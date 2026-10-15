# Blog MapTrotter — convention d’URL (V1)

**Schéma retenu : B2-A** — fichiers HTML publiés sous `/blog/{slug}.html`.

| Élément | Chemin |
|---------|--------|
| Listing | `/blog.html` (lit `blog-index.json`) |
| Article publié | `/blog/{slug}.html` |
| Source Markdown | `/blog/posts/{YYYY-MM-DD}-{slug}.md` |
| Catalogue | `/blog-index.json` |
| Template générateur | `/article.html` (`noindex`, placeholders `{{…}}`) |

## Slugs

- `kebab-case`, sans accents, ~60–80 caractères max.
- Locale : FR par défaut ; suffixe `-en` / `-es` si besoin (une seule règle).

## Ajouter un article (manuel)

1. Écrire le Markdown dans `blog/posts/`.
2. Cloner `article.html` → `blog/{slug}.html` et remplir les placeholders.
3. Ajouter l’entrée dans `blog-index.json` (`status: published`).
4. Ajouter l’URL dans `sitemap.xml`.

Le pipeline Gemini (phase C) automatisera ces étapes.
