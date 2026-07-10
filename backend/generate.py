"""
generate.py — Régénère le bulletin et les archives à partir de spectre.db.

Installation :
    pip install jinja2 --break-system-packages

Utilisation :
    python3 generate.py
    (à lancer juste après collector.py, voir README.md)
"""

import sqlite3
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from jinja2 import Environment, FileSystemLoader

DB_PATH = "spectre.db"
OUTPUT_DIR = "../"          # écrit à côté des pages existantes du site
TEMPLATES_DIR = "templates"

ICONS = {
    "ransomware": '<svg viewBox="0 0 48 48"><rect x="12" y="22" width="24" height="18" rx="2"/><path d="M18 22v-6a6 6 0 0112 0v2"/><path d="M24 30l-2 4h4l-2 4"/></svg>',
    "vulnerability": '<svg viewBox="0 0 48 48"><path d="M24 5l15 5v11c0 10-6.5 17-15 21-8.5-4-15-11-15-21V10z"/><circle cx="24" cy="24" r="5"/><path d="M24 16v3M24 29v3M17 24h3M28 24h3M19 19l2 2M27 19l-2 2M19 29l2-2M27 29l-2-2"/></svg>',
    "hacktivism": '<svg viewBox="0 0 48 48"><path d="M24 4l16 6v12c0 11-7 18-16 22C15 40 8 33 8 22V10z"/><path d="M24 14v8M24 26v2M17 17l3 3M31 17l-3 3M14 24h4M30 24h4M17 31l3-3M31 31l-3-3"/></svg>',
    "breach": '<svg viewBox="0 0 48 48"><path d="M6 16V11a2 2 0 012-2h10l4 4h18a2 2 0 012 2v3"/><path d="M6 16h36l-4 18a3 3 0 01-3 2.4H13a3 3 0 01-3-2.4z"/><path d="M24 24v6M22 33h4"/></svg>',
    "phishing": '<svg viewBox="0 0 48 48"><rect x="6" y="12" width="36" height="24" rx="2"/><path d="M6 14l18 14L42 14"/><path d="M30 30q4 2 4 6t-4 4"/></svg>',
    "other": '<svg viewBox="0 0 48 48"><rect x="8" y="18" width="32" height="14" rx="2"/><circle cx="15" cy="25" r="1.6"/><circle cx="21" cy="25" r="1.6"/><path d="M28 25h8"/><path d="M24 6l6 10h-12z"/><path d="M24 11v2"/></svg>',
}

def guess_category(title, summary):
    text = f"{title} {summary}".lower()
    if "ransomware" in text or "rançongiciel" in text or "chiffreur" in text:
        return "ransomware"
    if "anonymous" in text or "ddos" in text or "hacktivis" in text or "défacement" in text:
        return "hacktivism"
    if "breach" in text or "fuite de données" in text or "leaked" in text:
        return "breach"
    if "phishing" in text or "hameçonnage" in text:
        return "phishing"
    if "cve" in text or "vulnerab" in text or "vulnérab" in text:
        return "vulnerability"
    return "other"

SEVERITY_LABELS = {"critique": "Critique", "eleve": "Élevé", "moyen": "Moyen", "faible": "Faible"}
SEVERITY_CLASS  = {"critique": "sev-critical", "eleve": "sev-high", "moyen": "sev-medium", "faible": "sev-low"}

MONTHS = ["janvier","février","mars","avril","mai","juin","juillet",
          "août","septembre","octobre","novembre","décembre"]
DAYS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]

def french_date(dt):
    return f"{DAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month-1]} {dt.year}".capitalize()

def row_to_story(row):
    _, source, title, summary, link, severity, published_at, collected_at = row
    return {
        "source": source, "title": title, "summary": summary, "link": link,
        "severity": severity,
        "severity_label": SEVERITY_LABELS.get(severity, severity),
        "severity_class": SEVERITY_CLASS.get(severity, "sev-medium"),
        "icon": ICONS[guess_category(title, summary)],
        "published_at": published_at,
        # Par défaut : source unique. Un vrai calcul de corroboration nécessiterait
        # de regrouper les signaux par similarité de titre à travers les sources
        # (ex. rapprochement par mots-clés ou embeddings) — non implémenté ici.
        "confidence_label": "Source unique",
        "confidence_class": "conf-single",
    }

FRANCE_SOURCES = {"CERT-FR", "ANSSI", "ZATAZ"}
FRANCE_KEYWORDS = [
    "france", "français", "française", "hexagone", "hexagonal",
    # grandes villes françaises, pour repérer des cibles sans le mot "France" explicite
    "paris", "lyon", "marseille", "toulouse", "bordeaux", "lille",
    "strasbourg", "nantes", "rennes", "nice", "montpellier",
]

def is_france_related(source, title, summary, link):
    text = f"{title} {summary}".lower()
    if source in FRANCE_SOURCES:
        return True
    if any(k in text for k in FRANCE_KEYWORDS):
        return True
    try:
        domain = urlparse(link).netloc.lower()
        if domain.endswith(".fr"):
            return True
    except Exception:
        pass
    return False

def fetch_recent_france_alerts(conn, hours=24):
    """
    Renvoie la liste complète (pas seulement le nombre) des signaux des
    dernières `hours` heures glissantes considérés comme concernant la
    France. Fenêtre glissante plutôt que "jour calendaire" strict, pour
    éviter les effets de bord de fuseau horaire qui sous-comptaient.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT id, source, title, summary, link, severity, published_at, collected_at
        FROM alerts WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (since,)).fetchall()

    matches = []
    for r in rows:
        _, source, title, summary, link, severity, published_at, collected_at = r
        if is_france_related(source, title, summary, link):
            matches.append(row_to_story(r))
    return matches

def fetch_today(conn):
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = conn.execute("""
        SELECT id, source, title, summary, link, severity, published_at, collected_at
        FROM alerts WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (since,)).fetchall()
    return [row_to_story(r) for r in rows]

def fetch_archive(conn):
    rows = conn.execute("""
        SELECT id, source, title, summary, link, severity, published_at, collected_at
        FROM alerts WHERE severity IN ('critique','eleve') ORDER BY collected_at DESC LIMIT 200
    """).fetchall()
    groups = {}
    for r in rows:
        story = row_to_story(r)
        day = story["published_at"][:10] if story["published_at"] else "inconnue"
        groups.setdefault(day, []).append(story)
    return groups

import xml.sax.saxutils as saxutils

def generate_rss(stories):
    items = []
    for s in stories:
        items.append(f"""  <item>
    <title>{saxutils.escape('[' + s['severity_label'] + '] ' + s['title'])}</title>
    <link>{saxutils.escape(s['link'])}</link>
    <description>{saxutils.escape(s['summary'])}</description>
    <source>{saxutils.escape(s['source'])}</source>
    <pubDate>{saxutils.escape(s['published_at'])}</pubDate>
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>La Cyber Sphère — Bulletin de veille cyber</title>
  <link>https://example.com/la_cyber_sphere.html</link>
  <description>Alertes critiques et élevées, résumées et sourcées.</description>
  <language>fr-fr</language>
{chr(10).join(items)}
</channel>
</rss>
"""

def main():
    conn = sqlite3.connect(DB_PATH)
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False)

    today_stories = fetch_today(conn)
    france_alerts = fetch_recent_france_alerts(conn, hours=24)
    france_count = len(france_alerts)
    bulletin_tpl = env.get_template("bulletin.html")
    rendered_bulletin = bulletin_tpl.render(
        stories=today_stories, count=len(today_stories),
        france_count=france_count, france_alerts=france_alerts
    )
    with open(f"{OUTPUT_DIR}la_cyber_sphere.html", "w", encoding="utf-8") as f:
        f.write(rendered_bulletin)
    # index.html est une copie identique — c'est le nom que cherchent par défaut
    # la plupart des hébergeurs (Firebase, Netlify, GitHub Pages...) pour la
    # page d'accueil, sans dépendre d'une règle de redirection.
    with open(f"{OUTPUT_DIR}index.html", "w", encoding="utf-8") as f:
        f.write(rendered_bulletin)

    archive_groups = fetch_archive(conn)
    archive_tpl = env.get_template("archives.html")
    with open(f"{OUTPUT_DIR}archives.html", "w", encoding="utf-8") as f:
        f.write(archive_tpl.render(groups=archive_groups))

    with open(f"{OUTPUT_DIR}rss.xml", "w", encoding="utf-8") as f:
        f.write(generate_rss(today_stories))

    print(f"Généré : {len(today_stories)} signaux du jour, {sum(len(v) for v in archive_groups.values())} en archive.")
    conn.close()

if __name__ == "__main__":
    main()
