# HANDOFF — MapTrotterLanding

**Pour :** Timothée Guillaume  
**Date :** 2026-11-24  
**Repo :** [timotheeguillaume-creator/maptrotter-landing](https://github.com/timotheeguillaume-creator/maptrotter-landing)  
**Site live :** https://maptrotter.xyz/

---

## 1. Contexte

**MapTrotter** (produit) par **Xwalk** (société, ex-« xWalk ») — landing SEO / téléchargement, HTML statique déployé via **Cloudflare** (Workers/Pages, `wrangler.jsonc`).

Le Project Cursor **MapTrotterLanding** orchestre le blog SEO auto (cron Gemini → commit `main` → republish), le polish UI hero/FOMO, et la préparation social (comptes humains + webhook) côté app privée.

---

## 2. Avancement

| Chantier | État |
|----------|------|
| Pipeline SEO blog (Gemini free, quality gates, cron Tue/Thu 08:00 UTC) | **Live** — `publish_mode=commit` (fire-and-forget) |
| Matrice AU-first FR/EN/ES/IT/DE (~20k seeds) | **Live** — `data/keyword-dictionary.json` |
| Fallbacks Gemini (exit 4 / 503) + retry quality gates (exit 7) | **Mergé** (#19, #21) |
| IndexNow + sitemap/RSS sur commit | **Live** (si `INDEXNOW_KEY`) |
| Article Adelaide EN `last-minute-activities-in-adelaide-en` | **Publié** + posts AU suivants sur `main` |
| Brand/UI FOMO (splash, CTAs, pops, rocket Play, apple App Store) | **Mergé** (#10–#18) |
| Rename xWalk → **Xwalk** + privacy `legals.html` | **Mergé** (#20) |
| Audits repo app après connect GitHub (cloud + Bonbeck) | **Done** (MT-13, MT-14) — skeleton `marketing-studio/` dry-run only |
| Plans social + audit marketing | **For Review** (MT-11, MT-12) |

**Blog index :** ~13 posts dans `blog-index.json` (pilote FR + auto Newcastle, Sydney ES, Adelaide EN, Perth, Melbourne DE, Gold Coast IT, Brisbane ES, Canberra IT, Fremantle, Hobart DE, Geelong EN, Launceston IT, …).

---

## 3. État des fichiers / surface code

### Landing (ce repo)

| Zone | Chemins | Rôle |
|------|---------|------|
| Cron SEO | `.github/workflows/seo-blog-cron.yml` | Tue/Thu 08:00 UTC ; `publish_mode=commit` par défaut |
| Générateur | `scripts/generate-blog-post.py` | Orchestration Gemini + gates + publish |
| Lib blog | `scripts/blog_lib/` (`topic`, `gemini`, `gates`, `parse`, `render`, `catalog`) | Pick AU, API, qualité, HTML |
| IndexNow | `scripts/ping-indexnow.py` | Ping post-commit |
| Matrice | `data/keyword-dictionary.json` (+ `scripts/build-dictionary.py`) | ~20 218 seeds, 5 locales, 43 villes |
| Prompt | `prompts/maptrotter-blog.md` | Voix marque |
| Hero / UI | `index.html`, `assets/css/brand.css` | Splash, CTAs FOMO, pops, gags store |
| Pages | `blog.html`, `article.html`, `legals.html` | Listing, template, privacy Xwalk |
| Catalog live | `blog/`, `blog-index.json`, `sitemap.xml`, `feed.xml` | Articles + SEO |
| Deploy | `wrangler.jsonc`, `package.json` | Assets Cloudflare |
| Clé IndexNow publique | `/{INDEXNOW_KEY}.txt` à la racine (si secret posé) | Protocole IndexNow |

### App privée (hors ce repo)

`timotheeguillaume-creator/maptrotter` @ **`spike/map-core-native`** — `marketing-studio/` (social dry-run, `calendar.json` vide, `SOCIAL_PUBLISH` off), OAuth login ≠ posting, Fastlane dry-run. Voir audits store.

---

## 4. PRs & merges notables

| PR | Titre | Lien |
|----|-------|------|
| #3 | Pipeline Gemini blog (C2–C5) | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/3 |
| #4 | Fix modèle Gemini post-retirement 2.0 | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/4 |
| #5 | Matrice Australia-first + scoring clusters | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/5 |
| #6 | Unblock `publish_mode=pr` (permissions Actions) | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/6 |
| #7–#8 | Premiers articles auto (Newcastle EN, Sydney ES) | [#7](https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/7) · [#8](https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/8) |
| #9 | Schedule → `publish_mode=commit` | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/9 |
| #10–#18 | UI splash / langues / FOMO / pops / rocket / apple | [#10](https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/10) … [#18](https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/18) |
| #19 | Fallbacks Gemini exit 4 (503) | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/19 |
| #20 | Xwalk rename + privacy | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/20 |
| #21 | Retry quality gates exit 7 | https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/21 |

Supersédées (fermées sans merge) : [#1](https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/1), [#2](https://github.com/timotheeguillaume-creator/maptrotter-landing/pull/2).

---

## 5. Préférences figées

Source : `/cursor/stores/self/preferences.md` (2026-10-15+)

- **LLM blog :** Gemini free tier (+ retries / fallbacks), pas OpenAI  
- **Géo :** Australia-first (majors → secondary → Oceania → legacy)  
- **Langues :** FR, EN, ES, IT, DE  
- **Publish :** `publish_mode=commit` (auto-push `main`), pas draft PR par défaut  
- **Stores :** liens App Store / Play restent `#` jusqu’aux vrais IDs — **ne pas inventer**  
- **Auto-merge :** PRs landing du Project peuvent merger quand CI/preview vert

---

## 6. Reste à faire

### Humain (Timothée)

- [ ] **MT-15** Créer comptes marque **IG / TikTok / FB Page / X** (agents ne créent jamais de comptes)
- [ ] Choisir **Metricool vs Buffer** (ou Worker) → peupler `SOCIAL_WEBHOOK_URL` côté app
- [ ] Remplir `marketing-studio/calendar.json` **avant** `SOCIAL_PUBLISH=1`
- [ ] **MT-1** Fournir IDs App Store + Play → remplacer les `#` landing (et `EXPO_PUBLIC_*_STORE_LINK` app)

### Agents / suite Project

- [ ] **MT-11 / MT-12** Relire docs For Review : [social-automation-plan](/cursor/stores/self/docs/social-automation-plan.md), [marketing-stack-audit](/cursor/stores/self/docs/marketing-stack-audit.md)
- [ ] **MT-2** Suivre [stratégie SEO](/cursor/stores/self/docs/seo-coverage-strategy.md) (pillars AU, ~2 posts/sem, pas 12/jour)
- [ ] Optionnel : wiring blog → social packs (brief JSON post-cron → outbox / webhook)
- [ ] Brancher webhook + activer publish social seulement après comptes + calendar

### Tracker

Voir `/cursor/stores/self/notes.md` (Queued : MT-15, MT-16, MT-1, MT-2 ; For Review : MT-11, MT-12).

---

## 7. Blockers / non-négociables

1. **Agents ne créent jamais** de comptes sociaux (IG/TikTok/FB Page/X) — pas de signup / CAPTCHA / phone farm.  
2. **Auth OAuth ≠ posting** — Google / Apple / Facebook / Twitch dans l’app = login utilisateur ; le Facebook Developer app sert au login, **pas** à publier une Page.  
3. **Pas d’IDs store inventés** — liens restent `#` jusqu’à IDs réels.  
4. Social cron app reste **dry-run** tant que `SOCIAL_PUBLISH≠1` ou webhook absent / `calendar.json` vide.  
5. Cadence éditoriale : **~2 articles/semaine** (Gemini free) — matrice = réservoir, pas file de spam.

---

## 8. Liens utiles

| Ressource | URL / chemin |
|-----------|----------------|
| Repo landing | https://github.com/timotheeguillaume-creator/maptrotter-landing |
| Site live | https://maptrotter.xyz/ |
| Repo app (privé) | https://github.com/timotheeguillaume-creator/maptrotter (`spike/map-core-native`) |
| Plan SEO blog | [/cursor/stores/self/docs/seo-blog-automation-plan.md](/cursor/stores/self/docs/seo-blog-automation-plan.md) |
| Stratégie SEO | [/cursor/stores/self/docs/seo-coverage-strategy.md](/cursor/stores/self/docs/seo-coverage-strategy.md) |
| Matrice keywords | [/cursor/stores/self/docs/keyword-matrix-overview.md](/cursor/stores/self/docs/keyword-matrix-overview.md) |
| Plan social | [/cursor/stores/self/docs/social-automation-plan.md](/cursor/stores/self/docs/social-automation-plan.md) |
| Audit marketing | [/cursor/stores/self/docs/marketing-stack-audit.md](/cursor/stores/self/docs/marketing-stack-audit.md) |
| Préférences | [/cursor/stores/self/preferences.md](/cursor/stores/self/preferences.md) |
| Notes tracker | [/cursor/stores/self/notes.md](/cursor/stores/self/notes.md) |
| Audit app (cloud) | [/cursor/stores/self/internal/app-repo-audit.md](/cursor/stores/self/internal/app-repo-audit.md) |
| Audit app (Bonbeck) | [/cursor/stores/self/internal/app-repo-local-bonbeck.md](/cursor/stores/self/internal/app-repo-local-bonbeck.md) |

---

*Document généré pour handoff humain / prochain agent — sources store Project + git landing uniquement.*
