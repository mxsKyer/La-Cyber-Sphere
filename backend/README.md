# SPECTRE — backend de collecte

Ce dossier fait tourner le bulletin automatiquement : il interroge les
sources, classe les signaux par sévérité, et régénère les pages HTML
du site (`spectre-editorial.html` et `archives.html`).

## Installation

```
pip install -r requirements.txt --break-system-packages
```

## Utilisation manuelle

```
cd backend
python3 collector.py   # interroge les flux, remplit spectre.db
python3 generate.py    # régénère les pages HTML à partir de spectre.db
```

## Automatiser (cron, toutes les 15 minutes)

```
crontab -e
```

Ajouter :
```
*/15 * * * * cd /chemin/vers/spectre/backend && /usr/bin/python3 collector.py >> collector.log 2>&1 && /usr/bin/python3 generate.py >> generate.log 2>&1
```

## Automatiser (systemd timer — plus robuste, recommandé sur un serveur)

`/etc/systemd/system/spectre.service` :
```
[Unit]
Description=Collecte SPECTRE

[Service]
Type=oneshot
WorkingDirectory=/chemin/vers/spectre/backend
ExecStart=/usr/bin/python3 collector.py
ExecStartPost=/usr/bin/python3 generate.py
```

`/etc/systemd/system/spectre.timer` :
```
[Unit]
Description=Lance la collecte SPECTRE toutes les 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
```

Puis :
```
sudo systemctl enable --now spectre.timer
```

## Hébergement

Une fois les pages régénérées à chaque cycle, il suffit qu'un serveur web
(nginx, ou un hébergeur statique type Netlify/Vercel/GitHub Pages avec un
job de build qui repasse par ce script) serve le dossier. Le plus simple
sur un petit VPS : nginx pointé sur le dossier du site, et le cron ci-dessus
qui régénère les fichiers en place.

## Points d'attention

- **Droit d'auteur** : `summarize()` dans `collector.py` ne fait qu'une
  troncature simple pour la démo. En production, remplace-la par un appel
  à un modèle qui reformule réellement le contenu — ne jamais republier
  le texte intégral d'un flux RSS, même partiellement.
- **Fiabilité des flux** : vérifie régulièrement les URLs RSS listées dans
  `RSS_SOURCES` — les organismes changent parfois leurs chemins sans préavis.
- **CISA** publie son catalogue KEV en JSON plutôt qu'en RSS ; le format
  peut évoluer, à surveiller.
- **Débit** : respecte les conditions d'utilisation de chaque source
  (fréquence de sondage raisonnable — 15 à 30 minutes est largement
  suffisant pour ce type de veille).
