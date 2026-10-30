#!/usr/bin/env python3
"""
MapTrotter SEO blog generator — Google Gemini (free tier).

Pipeline:
  1. Pick topic from data/keyword-dictionary.json
  2. Call Gemini with retries/backoff (or --fixture / dry scaffolding)
  3. Parse frontmatter + Markdown + JSON-LD
  4. Quality gates
  5. Write blog/posts/*.md + blog/{slug}.html
  6. Update blog-index.json, sitemap.xml, feed.xml, dictionary usedCount

Usage:
  python3 scripts/generate-blog-post.py --dry-run --fixture scripts/fixtures/sample-gemini-response.md
  python3 scripts/generate-blog-post.py --locale fr
  DRY_RUN=1 GEMINI_API_KEY=... python3 scripts/generate-blog-post.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blog_lib import catalog, gates, gemini, parse, render, topic  # noqa: E402

log = logging.getLogger("blog.generate")


def build_prompt(topic_row: dict, prompt_path: Path, today: date) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    replacements = {
        "{{phrase}}": str(topic_row.get("phrase") or ""),
        "{{locale}}": str(topic_row.get("locale") or "fr"),
        "{{city}}": str(topic_row.get("city") or ""),
        "{{intent}}": str(topic_row.get("intent") or ""),
        "{{spotType}}": str(topic_row.get("spotType") or "null"),
        "{{date}}": today.isoformat(),
        "{{clusterId}}": str(topic_row.get("clusterId") or ""),
    }
    out = template
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


def recent_corpus(root: Path, index: dict) -> tuple[list[str], list[str]]:
    titles: list[str] = []
    bodies: list[str] = []
    for post in (index.get("posts") or [])[:5]:
        titles.append(str(post.get("title") or ""))
        src = post.get("source")
        if src:
            path = root / src.lstrip("/")
            if path.exists():
                text = path.read_text(encoding="utf-8")
                try:
                    _, body = parse.parse_frontmatter(text)
                    bodies.append(body)
                except ValueError:
                    bodies.append(text)
    return titles, bodies


def write_markdown(root: Path, meta: dict, body: str, json_ld: dict) -> Path:
    date_iso = str(meta["date"])[:10]
    slug = meta["slug"]
    posts_dir = root / "blog" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    path = posts_dir / f"{date_iso}-{slug}.md"
    # Rebuild frontmatter cleanly
    tags = meta.get("tags") or []
    if isinstance(tags, list):
        tags_s = "[" + ", ".join(json.dumps(t, ensure_ascii=False) for t in tags) + "]"
    else:
        tags_s = "[]"
    fm = "\n".join(
        [
            "---",
            f'title: {json.dumps(meta.get("title") or "", ensure_ascii=False)}',
            f'description: {json.dumps(meta.get("description") or "", ensure_ascii=False)}',
            f'slug: {json.dumps(slug, ensure_ascii=False)}',
            f'locale: {json.dumps(meta.get("locale") or "fr", ensure_ascii=False)}',
            f'city: {json.dumps(meta.get("city") or "", ensure_ascii=False)}',
            f'cluster: {json.dumps(meta.get("cluster") or "", ensure_ascii=False)}',
            f'date: {json.dumps(date_iso, ensure_ascii=False)}',
            f'category: {json.dumps(meta.get("category") or "Guides", ensure_ascii=False)}',
            f"tags: {tags_s}",
            f"readingMinutes: {int(meta.get('readingMinutes') or 5)}",
            f'status: "published"',
            f'keywordId: {json.dumps(meta.get("keywordId") or "", ensure_ascii=False)}',
            "---",
            "",
        ]
    )
    json_block = (
        "\n\n```json-ld\n"
        + json.dumps(json_ld, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    path.write_text(fm + body.strip() + json_block, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a MapTrotter blog post via Gemini")
    parser.add_argument("--dry-run", action="store_true", help="Validate & write under /tmp or skip catalog writes when set with FIXTURE_ONLY")
    parser.add_argument("--fixture", type=Path, help="Use a local Gemini response file (no API call)")
    parser.add_argument("--locale", type=str, default=None)
    parser.add_argument("--city", type=str, default=None)
    parser.add_argument("--slug-override", type=str, default=None)
    parser.add_argument("--skip-write", action="store_true", help="Run gates only; do not write files")
    parser.add_argument("--allow-short-fixture", action="store_true", help="Relax min word count for fixtures")
    args = parser.parse_args()

    dry = args.dry_run or os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    today = date.today()
    dict_path = ROOT / "data" / "keyword-dictionary.json"
    if not dict_path.exists():
        log.error("missing %s", dict_path)
        return 2
    dictionary = json.loads(dict_path.read_text(encoding="utf-8"))

    blog_index = catalog.load_blog_index(ROOT)
    recent_titles = [
        str(p.get("title") or "")
        for p in (blog_index.get("posts") or [])[:12]
        if p.get("title")
    ]

    picked = topic.pick_topic(
        dictionary,
        today=today,
        locale=args.locale,
        city=args.city,
        recent_titles=recent_titles,
    )
    if not picked:
        log.error("no active keyword to pick")
        return 2
    log.info(
        "topic id=%s phrase=%r city=%s locale=%s",
        picked.get("id"),
        picked.get("phrase"),
        picked.get("city"),
        picked.get("locale"),
    )

    prompt_path = ROOT / "prompts" / "maptrotter-blog.md"
    prompt = build_prompt(picked, prompt_path, today)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not args.fixture and not api_key:
        log.error(
            "GEMINI_API_KEY missing. Set the secret or pass --fixture for a dry run."
        )
        return 3

    # Regenerate on transient quality/parse failures so cron is not killed by
    # a single incomplete draft (e.g. missing json-ld from flash-lite).
    gate_attempts = int(os.environ.get("GATE_ATTEMPTS", "3"))
    if args.fixture:
        gate_attempts = 1  # fixture is deterministic — no point re-reading
    gate_attempts = max(1, min(gate_attempts, 5))

    index = catalog.load_blog_index(ROOT)
    recent_titles, recent_bodies = recent_corpus(ROOT, index)

    meta: dict = {}
    body = ""
    json_ld_raw: dict | list | None = None
    last_failures: list[str] = []
    correction = ""

    for attempt in range(1, gate_attempts + 1):
        prompt_attempt = prompt
        if correction:
            prompt_attempt = (
                prompt
                + "\n\n# CORRECTION OBLIGATOIRE (brouillon précédent rejeté)\n"
                + "Corrige STRICTEMENT ces échecs de qualité avant de renvoyer "
                + "l’article complet (frontmatter + Markdown + bloc ```json-ld``` "
                + "en fin de sortie) :\n"
                + correction
            )

        if args.fixture:
            raw = args.fixture.read_text(encoding="utf-8")
            log.info("using fixture %s (%s chars)", args.fixture, len(raw))
        else:
            assert api_key is not None
            try:
                log.info(
                    "gemini draft attempt=%s/%s",
                    attempt,
                    gate_attempts,
                )
                raw = gemini.call_gemini(prompt_attempt, api_key=api_key)
            except gemini.GeminiError as e:
                # Exit 4 = Gemini API failure (not quality gates / parse).
                log.error(
                    "gemini failed (exit 4) model=%s status=%s retryable=%s: %s",
                    getattr(e, "model", None),
                    getattr(e, "status", None),
                    getattr(e, "retryable", False),
                    e,
                )
                if e.status == 503 or (e.retryable and "high demand" in str(e).lower()):
                    log.error(
                        "hint: model capacity — fallbacks exhausted. "
                        "Cron will retry next schedule; or set GEMINI_MODEL / "
                        "GEMINI_MODEL_FALLBACKS (comma-separated)."
                    )
                elif e.status == 404:
                    log.error(
                        "hint: model id retired/missing — update DEFAULT_MODEL or "
                        "Actions var GEMINI_MODEL."
                    )
                elif e.status in (401, 403):
                    log.error("hint: check GEMINI_API_KEY secret.")
                return 4

        try:
            meta, body_with_ld = parse.parse_frontmatter(raw)
            body, json_ld_raw = parse.extract_json_ld(body_with_ld)
        except ValueError as e:
            last_failures = [f"parse error: {e}"]
            log.warning(
                "parse failed attempt=%s/%s: %s",
                attempt,
                gate_attempts,
                e,
            )
            correction = f"- {last_failures[0]}\n"
            if attempt < gate_attempts:
                continue
            log.error("parse error after %s attempt(s): %s", gate_attempts, e)
            return 5

        # Fill meta from topic when model omits fields
        meta.setdefault("locale", picked.get("locale") or "fr")
        meta.setdefault("city", picked.get("city"))
        meta.setdefault("cluster", picked.get("clusterId"))
        meta.setdefault("date", today.isoformat())
        meta["phrase"] = picked.get("phrase")
        meta["keywordId"] = picked.get("id")
        if args.slug_override:
            meta["slug"] = args.slug_override
        elif not meta.get("slug"):
            meta["slug"] = parse.slugify(
                str(meta.get("title") or picked.get("phrase") or "post"),
                locale=str(meta.get("locale") or "fr"),
            )

        # Idempotence: skip if HTML already exists
        html_path = ROOT / "blog" / f"{meta['slug']}.html"
        if html_path.exists() and not args.slug_override:
            log.warning(
                "slug already exists: %s — pick next topic manually or override",
                meta["slug"],
            )
            return 6

        # Salvage missing / incomplete JSON-LD from FAQ + meta before gates.
        # Keeps E-E-A-T structure (BlogPosting + FAQPage) without gutting checks.
        slug_preview = str(meta["slug"])
        canonical_preview = f"https://maptrotter.xyz/blog/{slug_preview}.html"
        if json_ld_raw is None:
            log.warning(
                "missing json-ld fence — synthesizing from meta/FAQ (attempt=%s)",
                attempt,
            )
        json_ld_for_gates = render.ensure_json_ld(
            json_ld_raw,
            meta=meta,
            canonical=canonical_preview,
            markdown=body,
        )

        gate = gates.run_gates(
            meta,
            body,
            json_ld_for_gates,
            recent_titles=recent_titles,
            recent_bodies=recent_bodies,
        )
        if args.allow_short_fixture or (args.fixture and dry):
            # Drop only the hard min-length failure for scaffolding fixtures
            gate.failures = [f for f in gate.failures if not f.startswith("too short:")]
            gate.ok = len(gate.failures) == 0

        if gate.ok:
            json_ld_raw = json_ld_for_gates
            log.info(
                "quality gates OK (words≈%s attempt=%s/%s)",
                gates.word_count(body),
                attempt,
                gate_attempts,
            )
            break

        last_failures = list(gate.failures)
        log.warning(
            "quality gates failed attempt=%s/%s:",
            attempt,
            gate_attempts,
        )
        for f in last_failures:
            log.warning("  - %s", f)
        correction = "".join(f"- {f}\n" for f in last_failures)
        if attempt < gate_attempts:
            log.info("regenerating draft after gate failure…")
            continue
    else:
        # Exhausted gate attempts
        log.error(
            "quality gates failed after %s attempt(s) (exit 7). Failures:",
            gate_attempts,
        )
        for f in last_failures:
            log.error("  - %s", f)
        log.error(
            "hint: exit 7 = content quality (structure/E-E-A-T/json-ld), "
            "not Gemini API. Pipeline regenerates up to GATE_ATTEMPTS "
            "(default 3). Check prompt compliance or raise GATE_ATTEMPTS."
        )
        return 7

    if args.skip_write:
        log.info("skip-write: exiting after gates")
        return 0

    canonical = f"https://maptrotter.xyz/blog/{meta['slug']}.html"
    json_ld = render.ensure_json_ld(
        json_ld_raw, meta=meta, canonical=canonical, markdown=body
    )
    body_html = render.markdown_to_html(body)
    template = render.load_template(ROOT)
    article_html = render.render_article_html(
        template=template,
        meta=meta,
        body_html=body_html,
        json_ld=json_ld,
    )

    write_root = ROOT
    if dry:
        out_dir = Path(os.environ.get("DRY_RUN_DIR") or "/tmp/maptrotter-blog-dry-run")
        out_dir.mkdir(parents=True, exist_ok=True)
        # Mirror structure under out_dir for inspection; also write into repo when DRY_RUN_WRITE_REPO=1
        if os.environ.get("DRY_RUN_WRITE_REPO", "").lower() in ("1", "true", "yes"):
            write_root = ROOT
            log.info("dry-run with DRY_RUN_WRITE_REPO=1 — writing into repo (no git commit here)")
        else:
            write_root = out_dir
            # Need template/assets paths relative — copy minimal tree
            (write_root / "blog" / "posts").mkdir(parents=True, exist_ok=True)
            log.info("dry-run output directory: %s", write_root)

    md_path = write_markdown(write_root if write_root == ROOT else write_root, meta, body, json_ld)
    # When dry-run to /tmp, still place HTML next to md
    if write_root != ROOT:
        html_out = write_root / "blog" / f"{meta['slug']}.html"
        html_out.parent.mkdir(parents=True, exist_ok=True)
        html_out.write_text(article_html, encoding="utf-8")
        # Also dump index/sitemap/rss into dry-run dir for inspection
        excerpt = catalog.excerpt_from_markdown(body)
        entry = catalog.post_entry_from_meta(meta, excerpt=excerpt)
        dry_index = catalog.load_blog_index(ROOT)
        catalog.upsert_post(dry_index, entry)
        catalog.save_blog_index(write_root, dry_index)
        catalog.write_sitemap(write_root, dry_index)
        catalog.write_rss(write_root, dry_index)
        (write_root / "prompt-used.md").write_text(prompt, encoding="utf-8")
        log.info("dry-run wrote %s and %s", md_path, html_out)
        return 0

    html_out = ROOT / "blog" / f"{meta['slug']}.html"
    html_out.parent.mkdir(parents=True, exist_ok=True)
    html_out.write_text(article_html, encoding="utf-8")

    excerpt = catalog.excerpt_from_markdown(body)
    entry = catalog.post_entry_from_meta(meta, excerpt=excerpt)
    catalog.upsert_post(index, entry)
    catalog.save_blog_index(ROOT, index)
    catalog.write_sitemap(ROOT, index)
    catalog.write_rss(ROOT, index)
    catalog.ensure_rss_link_in_html(ROOT / "blog.html")
    catalog.ensure_rss_link_in_html(ROOT / "index.html")

    topic.mark_used(dictionary, str(picked.get("id")), when=today)
    dict_path.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Emit machine-readable summary for Actions
    summary = {
        "slug": meta["slug"],
        "title": meta.get("title"),
        "path": f"/blog/{meta['slug']}.html",
        "canonical": canonical,
        "keywordId": picked.get("id"),
        "locale": meta.get("locale"),
        "dry_run": dry,
    }
    summary_path = Path(os.environ.get("GITHUB_WORKSPACE", str(ROOT))) / "blog-generate-summary.json"
    if os.environ.get("GITHUB_OUTPUT"):
        summary_path = ROOT / "blog-generate-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as gh:
            gh.write(f"slug={meta['slug']}\n")
            gh.write(f"canonical={canonical}\n")
            gh.write(f"title={meta.get('title')}\n")

    log.info("published %s", canonical)
    if dry:
        log.info("DRY_RUN complete (files written; caller should not push)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
