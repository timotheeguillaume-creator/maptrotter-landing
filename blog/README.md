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

Variable optionnelle : `GEMINI_MODEL` (défaut `gemini-2.0-flash`).

### Activer

1. Ajouter les secrets dans le repo GitHub.
2. Actions → **seo-blog-cron** → **Run workflow** avec `dry_run=true` (smoke).
3. Relancer avec `dry_run=false`, `publish_mode=pr` (rodage : PR draft).
4. Après validation humaine, merger → Cloudflare republie depuis `main`.
5. Plus tard : `publish_mode=commit` pour push direct + ping IndexNow.

Cron : mardi & jeudi 08:00 UTC. Cap ~2 posts/semaine. Retries Gemini : backoff 30s→240s.
