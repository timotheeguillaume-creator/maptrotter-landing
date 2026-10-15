#!/usr/bin/env python3
"""
Ping IndexNow + best-effort Google sitemap ping after a blog publish.

Secrets / env:
  INDEXNOW_KEY   — IndexNow key (also written to /{key}.txt if missing)
  SITE_HOST      — default maptrotter.xyz
  CANONICAL_URL  — primary URL to submit (article)
  EXTRA_URLS     — comma-separated extra URLs (optional)

Usage:
  INDEXNOW_KEY=... CANONICAL_URL=https://maptrotter.xyz/blog/slug.html \\
    python3 scripts/ping-indexnow.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("blog.indexnow")

SITE_HOST = os.environ.get("SITE_HOST", "maptrotter.xyz")
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def ensure_key_file(key: str) -> Path:
    path = ROOT / f"{key}.txt"
    if not path.exists():
        path.write_text(key + "\n", encoding="utf-8")
        log.info("wrote IndexNow key file %s (commit this once)", path.name)
    else:
        existing = path.read_text(encoding="utf-8").strip()
        if existing != key:
            log.warning("key file %s content differs from INDEXNOW_KEY — not overwriting", path.name)
    return path


def collect_urls(canonical: str | None) -> list[str]:
    urls: list[str] = []
    if canonical:
        urls.append(canonical)
    extras = os.environ.get("EXTRA_URLS", "")
    for part in extras.split(","):
        part = part.strip()
        if part:
            urls.append(part)
    # Always include listing + sitemap when publishing
    defaults = [
        f"https://{SITE_HOST}/blog.html",
        f"https://{SITE_HOST}/sitemap.xml",
        f"https://{SITE_HOST}/feed.xml",
    ]
    for u in defaults:
        if u not in urls:
            urls.append(u)
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def post_indexnow(key: str, url_list: list[str]) -> None:
    payload = {
        "host": SITE_HOST,
        "key": key,
        "keyLocation": f"https://{SITE_HOST}/{key}.txt",
        "urlList": url_list,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.info("IndexNow status=%s urls=%s", resp.status, len(url_list))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        # 200/202 OK; some engines return 202 Accepted
        if e.code in (200, 202):
            log.info("IndexNow accepted status=%s", e.code)
            return
        log.error("IndexNow HTTP %s: %s", e.code, body)
        raise


def ping_google_sitemap() -> None:
    sitemap = f"https://{SITE_HOST}/sitemap.xml"
    url = "https://www.google.com/ping?sitemap=" + urllib.parse.quote(sitemap, safe="")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            log.info("Google sitemap ping status=%s (best-effort)", resp.status)
    except Exception as e:
        # Google has deprecated / inconsistently supports this; never fail the job
        log.warning("Google sitemap ping skipped/failed: %s", e)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if not key:
        log.warning("INDEXNOW_KEY missing — skipping IndexNow (sitemap ping still attempted)")
        ping_google_sitemap()
        return 0

    if os.environ.get("SKIP_INDEXNOW", "").lower() in ("1", "true", "yes"):
        log.info("SKIP_INDEXNOW set — exiting")
        return 0

    ensure_key_file(key)
    canonical = os.environ.get("CANONICAL_URL") or os.environ.get("canonical")
    # Also read summary file if present
    summary = ROOT / "blog-generate-summary.json"
    if not canonical and summary.exists():
        try:
            canonical = json.loads(summary.read_text(encoding="utf-8")).get("canonical")
        except json.JSONDecodeError:
            pass

    urls = collect_urls(canonical)
    log.info("submitting %s URL(s) to IndexNow", len(urls))
    try:
        post_indexnow(key, urls)
    except Exception as e:
        log.error("IndexNow failed: %s", e)
        # Non-fatal for rodage: still ping sitemap
        ping_google_sitemap()
        return 0

    ping_google_sitemap()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
