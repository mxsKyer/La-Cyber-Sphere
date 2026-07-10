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
# Date du tout premier déploiement réel du site — sert de point de départ
# pour numéroter les éditions. À ne pas changer une fois en production.
LAUNCH_DATE = datetime(2026, 7, 6, tzinfo=timezone.utc).date()

def compute_edition_number():
    days_since_launch = (datetime.now(timezone.utc).date() - LAUNCH_DATE).days
    return max(1, days_since_launch + 1)

SEVERITY_RANK = {"critique": 0, "eleve": 1, "moyen": 2, "faible": 3}

def pick_lead_story(stories):
    """
    Choisit l'article vedette : le plus sévère parmi les signaux du jour.
    fetch_today() renvoie déjà les signaux triés du plus récent au plus
    ancien, donc en cas d'égalité de sévérité, min() conserve naturellement
    le plus récent (premier rencontré).
    """
    if not stories:
        return None
    return min(stories, key=lambda s: SEVERITY_RANK.get(s["severity"], 9))
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

from email.utils import parsedate_to_datetime

def parse_date(raw):
    """
    Les dates viennent de sources très hétérogènes (RFC 822 pour la plupart
    des flux RSS, ISO pour le JSON de la CISA...). Renvoie un datetime
    conscient du fuseau horaire, ou None si rien ne marche.
    """
    if not raw:
        return None
    for parser in (
        lambda s: parsedate_to_datetime(s),
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
    ):
        try:
            dt = parser(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None

def format_relative_time(raw):
    """Convertit une date brute en texte relatif lisible ('il y a 2 h')."""
    dt = parse_date(raw)
    if dt is None:
        return "date inconnue"

    delta = datetime.now(timezone.utc) - dt
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    if days < 7:
        return f"il y a {days} j"
    return dt.strftime("%d/%m/%Y")

def row_to_story(row):
    _, source, title, summary, link, severity, published_at, collected_at = row
    return {
        "source": source, "title": title, "summary": summary, "link": link,
        "severity": severity,
        "severity_label": SEVERITY_LABELS.get(severity, severity),
        "severity_class": SEVERITY_CLASS.get(severity, "sev-medium"),
        "icon": ICONS[guess_category(title, summary)],
        "published_at": format_relative_time(published_at),
        "published_at_raw": published_at,
        # Par défaut : source unique. Un vrai calcul de corroboration nécessiterait
        # de regrouper les signaux par similarité de titre à travers les sources
        # (ex. rapprochement par mots-clés ou embeddings) — non implémenté ici.
        "confidence_label": "Source unique",
        "confidence_class": "conf-single",
    }

FRANCE_SOURCES = {"CERT-FR", "ANSSI", "ZATAZ", "Cyberattaque.org"}
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
    """
    Le "briefing du jour" doit refléter ce qui vient vraiment d'être publié
    — pas ce que le collecteur a simplement vu passer pour la première fois
    (ce qui ferait resurgir de vieux articles dès qu'une nouvelle source est
    ajoutée). On élargit donc la requête SQL par sécurité, puis on filtre et
    on trie en Python sur la vraie date de publication.
    """
    safety_window = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    rows = conn.execute("""
        SELECT id, source, title, summary, link, severity, published_at, collected_at
        FROM alerts WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (safety_window,)).fetchall()

    now = datetime.now(timezone.utc)
    recent = []
    for r in rows:
        published_at = r[6]
        pub_dt = parse_date(published_at)
        # Si la date de publication est illisible, on retombe sur la date
        # de collecte plutôt que d'exclure silencieusement le signal.
        effective_dt = pub_dt or parse_date(r[7])
        if effective_dt and (now - effective_dt) <= timedelta(hours=24):
            recent.append((effective_dt, r))

    recent.sort(key=lambda x: x[0], reverse=True)
    return [row_to_story(r) for _, r in recent]

def fetch_archive(conn, max_days=365):
    since = (datetime.now(timezone.utc) - timedelta(days=max_days)).isoformat()
    rows = conn.execute("""
        SELECT id, source, title, summary, link, severity, published_at, collected_at
        FROM alerts WHERE severity IN ('critique','eleve') AND collected_at >= ?
        ORDER BY collected_at DESC LIMIT 500
    """, (since,)).fetchall()
    groups = {}
    for r in rows:
        collected_at = r[7]
        story = row_to_story(r)
        try:
            day = datetime.fromisoformat(collected_at).date().isoformat()
        except Exception:
            day = "inconnue"
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
    <pubDate>{saxutils.escape(s['published_at_raw'] or '')}</pubDate>
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

CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

RISK_WEIGHTS = {"critique": 10, "eleve": 5, "moyen": 2, "faible": 1}

def compute_risk_index(conn, days=13):
    """
    Indice de tension : somme pondérée des signaux par jour (Critique=10,
    Élevé=5, Moyen=2, Faible=1), plafonnée à 100. C'est une heuristique
    simple et documentée, pas un score scientifique — mais elle bouge
    vraiment avec le volume et la gravité réels des signaux collectés.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT severity, collected_at FROM alerts WHERE collected_at >= ?
    """, (since,)).fetchall()

    daily_totals = {}
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        daily_totals[day.isoformat()] = 0

    for severity, collected_at in rows:
        try:
            day = datetime.fromisoformat(collected_at).date().isoformat()
        except Exception:
            continue
        if day in daily_totals:
            daily_totals[day] += RISK_WEIGHTS.get(severity, 0)

    points = [min(100, daily_totals[d]) for d in sorted(daily_totals.keys())]
    current = points[-1] if points else 0
    week_ago = points[-8] if len(points) >= 8 else (points[0] if points else 0)
    delta = current - week_ago
    return {"value": current, "delta": delta, "points": points or [0]}

CATEGORY_LABELS = {
    "vulnerability": "Vulnérabilités / CVE",
    "ransomware": "Rançongiciels",
    "hacktivism": "Hacktivisme",
    "breach": "Fuites de données",
    "phishing": "Phishing",
    "other": "Autres",
}

def compute_category_breakdown(conn, days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT title, summary FROM alerts WHERE collected_at >= ?
    """, (since,)).fetchall()

    if not rows:
        return []

    counts = {}
    for title, summary in rows:
        cat = guess_category(title, summary)
        counts[cat] = counts.get(cat, 0) + 1

    total = sum(counts.values())
    breakdown = [
        {"label": CATEGORY_LABELS.get(cat, cat), "pct": round(count / total * 100)}
        for cat, count in counts.items()
    ]
    breakdown.sort(key=lambda x: x["pct"], reverse=True)
    return breakdown

def compute_cve_watch(conn, days=7, limit=4):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT title, summary, severity, collected_at FROM alerts
        WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (since,)).fetchall()

    seen = set()
    result = []
    for title, summary, severity, collected_at in rows:
        for cve_id in CVE_PATTERN.findall(f"{title} {summary}"):
            cve_id = cve_id.upper()
            if cve_id in seen:
                continue
            seen.add(cve_id)
            # Produit/contexte : les quelques mots autour du titre, tronqués.
            context = title if len(title) <= 40 else title[:40].rsplit(" ", 1)[0] + "…"
            result.append({
                "id": cve_id, "context": context,
                "severity_label": SEVERITY_LABELS.get(severity, severity),
                "severity_class": SEVERITY_CLASS.get(severity, "sev-medium"),
            })
            if len(result) >= limit:
                return result
    return result

def compute_week_stats(conn, days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT title, summary, severity, published_at, collected_at FROM alerts
        WHERE collected_at >= ?
    """, (since,)).fetchall()

    total = len(rows)
    critical = sum(1 for r in rows if r[2] == "critique")

    cve_ids = set()
    for title, summary, *_ in rows:
        cve_ids.update(m.upper() for m in CVE_PATTERN.findall(f"{title} {summary}"))

    # Délai moyen entre publication (source) et collecte (nous) — seulement
    # sur les entrées où la date de publication a pu être interprétée.
    delays = []
    for _, _, _, published_at, collected_at in rows:
        try:
            pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            col = datetime.fromisoformat(collected_at)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            delta_min = (col - pub).total_seconds() / 60
            if 0 <= delta_min <= 60 * 24 * 3:  # ignore les valeurs aberrantes (>3 jours)
                delays.append(delta_min)
        except Exception:
            continue
    avg_delay = round(sum(delays) / len(delays)) if delays else None

    return {
        "total": total, "critical": critical,
        "cve_count": len(cve_ids), "avg_delay": avg_delay,
    }

# Groupes documentés publiquement par des agences gouvernementales ou des
# éditeurs de sécurité reconnus (NCSC, CISA, Mandiant, ESET...). L'origine
# indiquée reprend l'attribution la plus courante dans ces rapports publics —
# ce n'est pas une déduction du script, seulement un rattachement à une
# information déjà établie. Étends cette liste au fil des lectures.
KNOWN_APT_GROUPS = [
    {"aliases": ["apt28", "fancy bear", "forest blizzard"], "canonical": "APT28 (Fancy Bear)", "origin": "Russie — GRU, unité 26165"},
    {"aliases": ["apt29", "cozy bear", "midnight blizzard"], "canonical": "APT29 (Cozy Bear)", "origin": "Russie — SVR (présumé)"},
    {"aliases": ["sandworm", "apt44", "seashell blizzard"], "canonical": "Sandworm (APT44)", "origin": "Russie — GRU, unité 74455"},
    {"aliases": ["lazarus", "tradertraitor", "apt38"], "canonical": "Lazarus Group", "origin": "Corée du Nord — Bureau général de reconnaissance"},
    {"aliases": ["kimsuky"], "canonical": "Kimsuky", "origin": "Corée du Nord (présumé)"},
    {"aliases": ["apt41", "double dragon"], "canonical": "APT41", "origin": "Chine (présumée)"},
    {"aliases": ["volt typhoon"], "canonical": "Volt Typhoon", "origin": "Chine (présumée)"},
    {"aliases": ["salt typhoon"], "canonical": "Salt Typhoon", "origin": "Chine (présumée)"},
    {"aliases": ["apt33", "elfin"], "canonical": "APT33", "origin": "Iran (présumé)"},
    {"aliases": ["apt35", "charming kitten"], "canonical": "APT35 (Charming Kitten)", "origin": "Iran (présumé)"},
    {"aliases": ["irgc"], "canonical": "Acteurs affiliés à l'IRGC", "origin": "Iran — Gardiens de la révolution"},
]

def compute_geopolitics(conn, days=30, limit=6):
    """
    Repère, dans les vrais articles collectés, les mentions de groupes déjà
    documentés publiquement. Ne déduit aucune attribution nouvelle — se
    contente de faire remonter les cas où une source a elle-même nommé un
    groupe connu.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT title, summary, source, link, severity, collected_at FROM alerts
        WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (since,)).fetchall()

    seen_groups = set()
    result = []
    for title, summary, source, link, severity, collected_at in rows:
        text = f"{title} {summary}".lower()
        for group in KNOWN_APT_GROUPS:
            if group["canonical"] in seen_groups:
                continue
            if any(alias in text for alias in group["aliases"]):
                seen_groups.add(group["canonical"])
                result.append({
                    "actor": group["canonical"],
                    "origin": group["origin"],
                    "activity": title,
                    "category": CATEGORY_LABELS.get(guess_category(title, summary), "Non précisé"),
                    "severity_label": SEVERITY_LABELS.get(severity, severity),
                    "severity_class": SEVERITY_CLASS.get(severity, "sev-medium"),
                    "source": source,
                    "link": link,
                })
                if len(result) >= limit:
                    return result
    return result

def compute_last_sync(conn):
    row = conn.execute("SELECT MAX(collected_at) FROM alerts").fetchone()
    return row[0] if row and row[0] else None

# ---------------------------------------------------------------------------
def main():
    conn = sqlite3.connect(DB_PATH)
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False)

    today_stories = fetch_today(conn)
    lead = pick_lead_story(today_stories)
    # Le briefing du dessous n'inclut pas l'article déjà mis à la une, pour
    # éviter de le lire deux fois sur la même page.
    briefing_stories = [s for s in today_stories if s is not lead]
    edition_number = compute_edition_number()

    france_alerts = fetch_recent_france_alerts(conn, hours=24)
    france_count = len(france_alerts)
    risk = compute_risk_index(conn)
    categories = compute_category_breakdown(conn)
    cve_watch = compute_cve_watch(conn)
    week_stats = compute_week_stats(conn)
    geopolitics = compute_geopolitics(conn)
    last_sync = compute_last_sync(conn)

    bulletin_tpl = env.get_template("bulletin.html")
    rendered_bulletin = bulletin_tpl.render(
        stories=briefing_stories, count=len(today_stories),
        france_count=france_count, france_alerts=france_alerts,
        lead=lead, edition_number=edition_number,
        risk=risk, categories=categories, cve_watch=cve_watch,
        week_stats=week_stats, geopolitics=geopolitics, last_sync=last_sync
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
