# Blog MapTrotter — convention d’URL (V1)

**Schéma retenu : B2-A** — fichiers HTML publiés sous `/blog/{slug}.html`.

| Élément | Chemin |
|---------|--------|
| Listing | `/blog.html` (lit `blog-index.json`) |
| Article publié | `/blog/{slug}.html` |
| Source Markdown | `/blog/posts/{YYYY-MM-DD}-{slug}.md` |
| Catalogue | `/blog-index.json` |
| Template générateur | `/article.html` (`noindex`, placeholders `{{…}}`) |
| RSS | `/feed.xml` |
| Prompt Gemini | `/prompts/maptrotter-blog.md` |
| Dictionary | `/data/keyword-dictionary.json` |
| Générateur | `/scripts/generate-blog-post.py` |
| IndexNow | `/scripts/ping-indexnow.py` |
| Cron | `.github/workflows/seo-blog-cron.yml` |

## Placeholders du template (`article.html`)

`{{LANG}}`, `{{TITLE}}`, `{{DESCRIPTION}}`, `{{CANONICAL}}`, `{{DATE_ISO}}`, `{{DATE_LABEL}}`, `{{CATEGORY}}`, `{{READING_MINUTES}}`, `{{BODY_HTML}}`, `{{OG_IMAGE}}`, `{{JSON_LD}}`

Le générateur remplace aussi `noindex` → `index, follow` sur les pages publiées.

## Slugs

- `kebab-case`, sans accents, ~60–80 caractères max.
- Locale : FR par défaut ; suffixe `-en` / `-es` si besoin (une seule règle).

## Ajouter un article (manuel)

1. Écrire le Markdown dans `blog/posts/` (Direct Answer + FAQ + CTA).
2. Cloner `article.html` → `blog/{slug}.html` et remplir les placeholders (ou lancer le script).
3. Ajouter l’entrée dans `blog-index.json` (`status: published`).
4. Régénérer `sitemap.xml` + `feed.xml`.

## Pipeline Gemini (auto, ~2×/semaine)

```bash
# Dry-run local sans clé API (fixture)
python3 scripts/generate-blog-post.py --dry-run \
  --fixture scripts/fixtures/sample-gemini-response.md

# Live (nécessite GEMINI_API_KEY)
GEMINI_API_KEY=... python3 scripts/generate-blog-post.py --locale fr
```

### Secrets GitHub Actions

| Secret | Obligatoire | Rôle |
|--------|-------------|------|
| `GEMINI_API_KEY` | oui | Google AI Studio / Gemini API (free tier) |
| `INDEXNOW_KEY` | recommandé | IndexNow + fichier public `/{key}.txt` |
| `SEO_CRON_TOKEN` | optionnel | PAT (repo + pull requests) si `GITHUB_TOKEN` ne peut pas ouvrir de PR |

Variables optionnelles : `GEMINI_MODEL` (défaut `gemini-3.8-flash`) ; `GEMINI_MODEL_FALLBACKS` (défaut `gemini-3.6-flash,gemini-3.5-flash-lite`) si le modèle principal renvoie 503 high-demand ; `GATE_ATTEMPTS` (défaut `3`) — régénère le brouillon si les quality gates / parse échouent (exit 7 seulement après épuisement).

### Permissions Actions (obligatoire pour `publish_mode=pr`)

Sans PAT `SEO_CRON_TOKEN`, activer dans le repo :

**Settings → Actions → General → Workflow permissions**

- Workflow permissions : **Read and write**
- Cocher **Allow GitHub Actions to create and approve pull requests**

Sans cette case, le cron génère + push la branche puis échoue à `gh pr create` (exit 8) avec le message GraphQL *GitHub Actions is not permitted to create or approve pull requests*.

### Activer

1. Ajouter les secrets dans le repo GitHub (`GEMINI_API_KEY`, `INDEXNOW_KEY` recommandé).
2. Actions → **seo-blog-cron** → **Run workflow** avec `dry_run=true` (smoke).
3. Cron programmé (mar/jeu 08:00 UTC) : `publish_mode=commit` — push direct sur `main` + ping IndexNow si `INDEXNOW_KEY` est défini.
4. Manuel (`workflow_dispatch`) : choisir `publish_mode=commit` (défaut fire-and-forget) ou `pr` (PR draft / rodage ; nécessite la case Actions ci-dessus ou `SEO_CRON_TOKEN`).

Cron : mardi & jeudi 08:00 UTC. Cap ~2 posts/semaine. Retries Gemini : 3 tentatives/modèle (backoff 20s→80s), puis fallbacks. Quality gates : jusqu’à `GATE_ATTEMPTS` (3) régénérations ; JSON-LD manquant synthétisé depuis FAQ/meta quand possible.
