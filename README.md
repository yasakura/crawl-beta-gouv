# crawl-beta-gouv

Alerte mail automatique pour les offres d'emploi de la communauté **beta.gouv.fr**
publiées sur [Welcome to the Jungle](https://www.welcometothejungle.com/fr/companies/communaute-beta-gouv/jobs).

Tourne en GitHub Actions toutes les 6 heures, compare la liste courante à `state.json`
(versionné dans le repo), et envoie un mail récapitulant les nouvelles offres.

## Fonctionnement

1. `crawl.py` interroge l'index Algolia public que WTJ utilise sur son propre
   site (clés en clair — ce sont des clés *search-only* côté navigateur).
2. Il filtre sur l'organisation `communaute-beta-gouv` et le site `wttj_fr`.
3. Il compare les références aux `known_refs` de `state.json`.
4. S'il y a du nouveau, il envoie **un seul mail** listant toutes les offres
   inédites, puis met `state.json` à jour.
5. Le workflow committe `state.json` pour que le prochain run sache ce qui
   était déjà connu.

Au premier run, si `state.json` n'existe pas, il est créé silencieusement —
aucun mail n'est envoyé pour éviter un flood initial. Ici le repo est déjà
pré-seedé avec les 8 offres en ligne au 2026-04-17, donc le premier run
CI n'enverra rien.

## Configuration

### 1. Mot de passe d'application Gmail

1. Activer la validation en deux étapes : https://myaccount.google.com/security
2. Créer un mot de passe d'application : https://myaccount.google.com/apppasswords
   (nommer l'app « crawl-beta-gouv » par ex.)
3. Récupérer le mot de passe à 16 caractères.

### 2. Secrets GitHub

Dans **Settings → Secrets and variables → Actions → New repository secret** :

| Secret      | Valeur                                   |
| ----------- | ---------------------------------------- |
| `SMTP_USER` | ton adresse Gmail (ex. `moi@gmail.com`)  |
| `SMTP_PASS` | le mot de passe d'application à 16 car.  |
| `MAIL_TO`   | destinataire (ex. `tu@exemple.tld`) |
| `MAIL_FROM` | *(optionnel)* adresse d'expédition. Défaut = `SMTP_USER`. |
| `SMTP_HOST` | *(optionnel)* défaut `smtp.gmail.com`    |
| `SMTP_PORT` | *(optionnel)* défaut `465` (SSL). Mettre `587` pour STARTTLS. |

### 3. Permissions du workflow

Le workflow a besoin de pousser `state.json`. Dans
**Settings → Actions → General → Workflow permissions**, cocher
**Read and write permissions** (ou laisser le défaut si déjà ouvert).

## Lancement

- **Auto** : GitHub Actions, toutes les 6 h (`cron: "17 */6 * * *"`).
- **Manuel** : onglet *Actions → crawl-beta-gouv → Run workflow*.

## Tester en local

```bash
# Voir ce qui serait envoyé, sans toucher au state ni envoyer de mail :
python3 crawl.py --dry-run

# Forcer la reseed (par ex. après édition manuelle) :
python3 crawl.py --seed

# Test d'envoi réel (exporter les secrets dans l'env du shell) :
export SMTP_USER=... SMTP_PASS=... MAIL_TO=...
python3 crawl.py
```

## Changer la fréquence

Modifier le `cron` dans `.github/workflows/crawl.yml`. Attention : GitHub
Actions peut retarder un cron de plusieurs minutes selon la charge. Ne pas
descendre sous `*/30` (toutes les 30 min) — l'index WTJ ne bouge pas si vite.

## Si les offres ne s'affichent plus

Cela veut probablement dire que WTJ a changé sa clé Algolia ou son schéma.
Les constantes en tête de `crawl.py` (`ALGOLIA_APP_ID`, `ALGOLIA_API_KEY`,
`ORG_SLUG_IN_INDEX`) sont à re-vérifier depuis la page publique — elles sont
toutes exposées côté client.
