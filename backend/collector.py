"""
collector.py — Collecte les signaux cyber depuis les sources publiques
et les stocke dans une base SQLite locale (spectre.db).

Installation :
    pip install feedparser requests --break-system-packages

Utilisation :
    python3 collector.py

À lancer périodiquement (cron / systemd timer), voir README.md.
"""

import sqlite3
import feedparser
import requests
import hashlib
import re
from datetime import datetime, timezone

DB_PATH = "spectre.db"

# ---------------------------------------------------------------------------
# 1. SOURCES — flux RSS publics. Vérifie régulièrement que ces URLs sont
#    toujours valides : les organismes changent parfois leurs chemins de flux.
# ---------------------------------------------------------------------------
RSS_SOURCES = [
    {"name": "CERT-FR — Avis",   "url": "https://www.cert.ssi.gouv.fr/avis/feed"},
    {"name": "CERT-FR — Alertes","url": "https://www.cert.ssi.gouv.fr/alerte/feed"},
    {"name": "The Hacker News",  "url": "https://feeds.feedburner.com/TheHackersNews"},
    {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/"},
    {"name": "Krebs on Security","url": "https://krebsonsecurity.com/feed/"},
    {"name": "ZATAZ",            "url": "https://www.zataz.com/feed/"},
    {"name": "Cyberattaque.org", "url": "https://www.cyberattaque.org/feed/"},
    # The Record (Recorded Future News) — bonne couverture géopolitique et
    # étatique, complète utilement la section interétatique.
    {"name": "The Record",       "url": "https://therecord.media/feed/"},
    # NCSC (Royaume-Uni) — équivalent britannique de l'ANSSI, source
    # officielle qui nomme régulièrement les groupes APT dans ses avis.
    {"name": "NCSC UK",          "url": "https://www.ncsc.gov.uk/api/1/services/v1/news-rss-feed.xml"},
]

# CISA publie son catalogue KEV en JSON plutôt qu'en RSS classique.
CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

# ---------------------------------------------------------------------------
# 2. CLASSIFICATION — scoring de sévérité par mots-clés.
#    Volontairement simple : à affiner avec un vrai modèle si besoin.
# ---------------------------------------------------------------------------
KEYWORDS_CRITICAL = [
    "exploited in the wild", "zero-day", "0-day", "activement exploitée",
    "ransomware", "rançongiciel", "remote code execution", "rce",
    "critical vulnerability", "faille critique",
]
KEYWORDS_HIGH = [
    "data breach", "fuite de données", "ddos", "denial of service",
    "hacktivist", "anonymous", "leaked", "compromised", "compromis",
]
KEYWORDS_MEDIUM = [
    "patch", "correctif", "update available", "vulnerability", "vulnérabilité",
]

def classify_severity(title, summary):
    text = f"{title} {summary}".lower()
    if any(k in text for k in KEYWORDS_CRITICAL):
        return "critique"
    if any(k in text for k in KEYWORDS_HIGH):
        return "eleve"
    if any(k in text for k in KEYWORDS_MEDIUM):
        return "moyen"
    return "faible"

def summarize(title, summary, max_len=220):
    """
    Résumé simplifié pour la démo : tronque proprement le texte de l'agrégateur.
    En production, remplacer par un appel à un modèle de résumé qui reformule
    réellement le contenu (voir note dans README.md — ne jamais republier
    le texte intégral d'une source).
    """
    clean = re.sub(r"<[^>]+>", "", summary or "").strip()
    if len(clean) <= max_len:
        return clean
    return clean[:max_len].rsplit(" ", 1)[0] + "…"

def make_id(link):
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

# ---------------------------------------------------------------------------
# 3. BASE DE DONNÉES
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            link TEXT NOT NULL,
            severity TEXT NOT NULL,
            published_at TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def insert_alert(conn, source, title, summary, link, severity, published_at):
    conn.execute("""
        INSERT OR IGNORE INTO alerts
        (id, source, title, summary, link, severity, published_at, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        make_id(link), source, title.strip(), summary, link, severity,
        published_at, datetime.now(timezone.utc).isoformat()
    ))

# ---------------------------------------------------------------------------
# 4. COLLECTE
# ---------------------------------------------------------------------------
def collect_rss(conn):
    for src in RSS_SOURCES:
        print(f"[collecte] {src['name']} …")
        try:
            feed = feedparser.parse(src["url"])
        except Exception as e:
            print(f"  ! échec : {e}")
            continue
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            summary_raw = entry.get("summary", "") or entry.get("description", "")
            link = entry.get("link", "")
            if not link:
                continue
            published = entry.get("published", "") or datetime.now(timezone.utc).isoformat()
            severity = classify_severity(title, summary_raw)
            summary = summarize(title, summary_raw)
            insert_alert(conn, src["name"], title, summary, link, severity, published)

def collect_cisa_kev(conn):
    print("[collecte] CISA — Catalogue KEV …")
    try:
        resp = requests.get(CISA_KEV_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ! échec : {e}")
        return
    for vuln in data.get("vulnerabilities", [])[:20]:
        cve_id = vuln.get("cveID", "")
        title = f"{cve_id} — {vuln.get('vulnerabilityName', '')}"
        summary = vuln.get("shortDescription", "")
        link = f"https://www.cisa.gov/known-exploited-vulnerabilities-catalog?search_api_fulltext={cve_id}"
        published = vuln.get("dateAdded", "")
        # Toute entrée du catalogue KEV est par définition exploitée activement.
        insert_alert(conn, "CISA — Catalogue KEV", title, summary, link, "critique", published)

def main():
    conn = init_db()
    collect_rss(conn)
    collect_cisa_kev(conn)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    print(f"Terminé. {total} signaux en base au total.")
    conn.close()

if __name__ == "__main__":
    main()
