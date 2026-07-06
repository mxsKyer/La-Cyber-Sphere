# La Cyber Sphère

Bulletin de veille cyber : collecte automatique, résumés originaux et sourcés,
archives, quiz quotidien. Voir `backend/README.md` pour le détail du
fonctionnement de la collecte.

## Structure du dépôt

```
la_cyber_sphere.html   → le bulletin (page d'accueil)
archives.html          → historique des signaux Critique/Élevé
quiz.html              → quiz quotidien
mentions-legales.html  → gabarit à compléter avant mise en ligne publique
rss.xml                → flux RSS régénéré automatiquement
backend/
  collector.py          → interroge les sources et alimente spectre.db
  generate.py           → régénère les pages HTML + le flux RSS à partir de spectre.db
  requirements.txt
  templates/            → gabarits Jinja2 utilisés par generate.py
firebase.json           → configuration Firebase Hosting
.firebaserc              → ID du projet Firebase (à personnaliser)
.github/workflows/
  update-and-deploy.yml  → automatisation : collecte + génération + déploiement
```

## Déploiement complet, étape par étape

### 1. Créer le dépôt GitHub

1. Va sur [github.com](https://github.com), crée un compte si besoin.
2. Clique sur **New repository**, donne-lui un nom (ex. `la-cyber-sphere`),
   laisse-le en **Public** ou **Private** selon ton choix, ne coche aucune
   case d'initialisation (pas de README auto), clique sur **Create repository**.
3. Sur ta machine, dans le dossier contenant tous ces fichiers :

```bash
git init
git add .
git commit -m "Version initiale du site"
git branch -M main
git remote add origin https://github.com/TON-COMPTE/la-cyber-sphere.git
git push -u origin main
```

### 2. Créer le projet Firebase

1. Va sur [console.firebase.google.com](https://console.firebase.google.com),
   connecte-toi avec un compte Google.
2. **Ajouter un projet**, donne-lui un nom, note l'**ID du projet** affiché
   (différent du nom si celui-ci était déjà pris).
3. Pas besoin d'activer Google Analytics pour ce projet.

### 3. Installer les outils Firebase en local

```bash
npm install -g firebase-tools
firebase login
```

Cette dernière commande ouvre le navigateur pour te connecter avec le même
compte Google que celui utilisé à l'étape 2.

### 4. Relier le dépôt à Firebase et configurer le déploiement automatique

Toujours dans le dossier du projet (celui avec `firebase.json`) :

```bash
firebase init hosting:github
```

Réponds aux questions dans cet ordre :
- **Quel projet Firebase ?** → sélectionne celui créé à l'étape 2
- **Quel dépôt GitHub ?** → `TON-COMPTE/la-cyber-sphere`
- **Lancer un script de build avant chaque déploiement ?** → **Non**
  (le site est déjà généré par `generate.py`, pas de build JS à faire)
- **Déployer automatiquement sur la branche live quand une PR est fusionnée ?**
  → réponds comme tu veux ; ce n'est pas ce mécanisme qui sera utilisé
  (voir étape 6), tu peux répondre Non sans problème

Cette commande crée automatiquement un secret nommé `FIREBASE_SERVICE_ACCOUNT`
dans les paramètres de ton dépôt GitHub — c'est celui que le workflow fourni
utilise déjà, aucune action supplémentaire n'est nécessaire de ce côté.

### 5. Personnaliser les deux fichiers avec l'ID du projet

Remplace `REMPLACE-PAR-L-ID-DE-TON-PROJET-FIREBASE` par l'ID noté à l'étape 2
dans ces deux fichiers :
- `.firebaserc`
- `.github/workflows/update-and-deploy.yml` (ligne `projectId:`)

### 6. Pousser les changements et vérifier

```bash
git add .
git commit -m "Configuration Firebase"
git push
```

Va ensuite dans l'onglet **Actions** de ton dépôt GitHub : le workflow
"Mise à jour et déploiement de La Cyber Sphère" doit apparaître. Il se
déclenche tout seul toutes les 30 minutes, mais tu peux aussi le lancer
manuellement tout de suite via le bouton **Run workflow** (grâce à la ligne
`workflow_dispatch` du fichier) pour vérifier que tout fonctionne sans
attendre.

### 7. Voir le site en ligne

Une fois le workflow terminé (statut vert), le site est accessible à :
```
https://TON-ID-DE-PROJET.web.app
```
ou
```
https://TON-ID-DE-PROJET.firebaseapp.com
```

### 8. (Optionnel) Nom de domaine personnalisé

Voir la section dédiée plus bas, ou directement dans la console Firebase :
Hosting → **Ajouter un domaine personnalisé**.

## Avant une mise en ligne publique réelle

- Complète `mentions-legales.html` (encore des champs `[à renseigner]`)
- Vérifie que les sources RSS listées dans `backend/collector.py` sont
  toujours valides (les organismes changent parfois leurs flux)
- Relis `backend/README.md` pour les bonnes pratiques de fréquence de
  collecte et de respect du droit d'auteur
