"""Update blog-index.json, sitemap.xml, feed.xml after a new post."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.dom import minidom

SITE = "https://maptrotter.xyz"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def load_blog_index(root: Path) -> dict[str, Any]:
    path = root / "blog-index.json"
    if not path.exists():
        return {
            "version": 1,
            "updated": date.today().isoformat(),
            "urlScheme": "B2-A",
            "urlPattern": "/blog/{slug}.html",
            "localeRule": "suffix optional: -fr / -en / -es (omit for default FR)",
            "posts": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_post(index: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    posts = index.setdefault("posts", [])
    slug = entry["slug"]
    for i, p in enumerate(posts):
        if p.get("slug") == slug:
            posts[i] = entry
            break
    else:
        posts.append(entry)
    posts.sort(key=lambda p: p.get("date") or "", reverse=True)
    index["updated"] = date.today().isoformat()
    return index


def save_blog_index(root: Path, index: dict[str, Any]) -> None:
    path = root / "blog-index.json"
    path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def post_entry_from_meta(meta: dict[str, Any], *, excerpt: str) -> dict[str, Any]:
    slug = meta["slug"]
    date_iso = str(meta.get("date") or date.today().isoformat())[:10]
    return {
        "slug": slug,
        "title": meta.get("title"),
        "description": meta.get("description"),
        "excerpt": excerpt[:160],
        "date": date_iso,
        "dateModified": date_iso,
        "locale": meta.get("locale") or "fr",
        "city": meta.get("city"),
        "cluster": meta.get("cluster"),
        "category": meta.get("category") or "Guides",
        "tags": meta.get("tags") or [],
        "readingMinutes": meta.get("readingMinutes") or 5,
        "path": f"/blog/{slug}.html",
        "source": f"/blog/posts/{date_iso}-{slug}.md",
        "status": "published",
        "image": "/splash.png",
        "keywordId": meta.get("keywordId"),
    }


def excerpt_from_markdown(md: str) -> str:
    # Prefer Direct Answer paragraph
    m = re_search_da(md)
    if m:
        return " ".join(m.split())[:160]
    for line in md.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line[:160]
    return ""


def re_search_da(md: str) -> str | None:
    import re

    m = re.search(
        r"(?im)^##\s*Direct Answer\s*\n+(.+?)(?=\n##\s|\Z)",
        md,
        re.DOTALL,
    )
    return m.group(1).strip() if m else None


def write_sitemap(root: Path, index: dict[str, Any]) -> None:
    today = date.today().isoformat()
    urls: list[tuple[str, str, str, str]] = [
        (f"{SITE}/", today, "weekly", "1.0"),
        (f"{SITE}/blog.html", today, "weekly", "0.8"),
    ]
    for post in index.get("posts") or []:
        if post.get("status") != "published":
            continue
        loc = f"{SITE}{post['path']}"
        lastmod = post.get("dateModified") or post.get("date") or today
        urls.append((loc, str(lastmod)[:10], "monthly", "0.7"))
    urls.append((f"{SITE}/legals.html", today, "monthly", "0.3"))

    # Build with ElementTree + pretty print
    ET.register_namespace("", NS)
    urlset = ET.Element(f"{{{NS}}}urlset")
    for loc, lastmod, freq, prio in urls:
        u = ET.SubElement(urlset, f"{{{NS}}}url")
        ET.SubElement(u, f"{{{NS}}}loc").text = loc
        ET.SubElement(u, f"{{{NS}}}lastmod").text = lastmod
        ET.SubElement(u, f"{{{NS}}}changefreq").text = freq
        ET.SubElement(u, f"{{{NS}}}priority").text = prio

    rough = ET.tostring(urlset, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="UTF-8")
    # minidom adds XML declaration; normalize blank lines
    text = pretty.decode("utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    (root / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_rss(root: Path, index: dict[str, Any]) -> None:
    posts = [
        p
        for p in (index.get("posts") or [])
        if p.get("status") == "published"
    ]
    posts = sorted(posts, key=lambda p: p.get("date") or "", reverse=True)[:50]

    items_xml: list[str] = []
    for p in posts:
        title = _xml_escape(str(p.get("title") or ""))
        link = f"{SITE}{p['path']}"
        desc = _xml_escape(str(p.get("description") or p.get("excerpt") or "")[:300])
        guid = link
        pub = _rss_date(str(p.get("date") or date.today().isoformat()))
        lang = p.get("locale") or "fr"
        items_xml.append(
            f"""    <item>
      <title>{title}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{guid}</guid>
      <pubDate>{pub}</pubDate>
      <description>{desc}</description>
      <language>{lang}</language>
    </item>"""
        )

    last_build = format_datetime(datetime.now(timezone.utc))
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Le Radar MapTrotter</title>
    <link>{SITE}/blog.html</link>
    <description>Guides locaux, rencontres et spots authentiques — MapTrotter</description>
    <language>fr</language>
    <lastBuildDate>{last_build}</lastBuildDate>
    <image>
      <url>{SITE}/splash.png</url>
      <title>MapTrotter</title>
      <link>{SITE}/blog.html</link>
    </image>
{chr(10).join(items_xml)}
  </channel>
</rss>
"""
    (root / "feed.xml").write_text(feed, encoding="utf-8")


def _rss_date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    dt = datetime(d.year, d.month, d.day, 8, 0, 0, tzinfo=timezone.utc)
    return format_datetime(dt)


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def ensure_rss_link_in_html(path: Path) -> bool:
    """Add alternate RSS link in <head> if missing. Returns True if modified."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if 'type="application/rss+xml"' in text:
        return False
    needle = '<link rel="canonical"'
    idx = text.find(needle)
    if idx == -1:
        # fallback: after charset
        needle = "<head>"
        idx = text.find(needle)
        if idx == -1:
            return False
        insert_at = idx + len(needle)
        snippet = (
            '\n  <link rel="alternate" type="application/rss+xml" '
            'title="Le Radar MapTrotter" href="/feed.xml" />'
        )
        path.write_text(text[:insert_at] + snippet + text[insert_at:], encoding="utf-8")
        return True
    # insert before canonical line
    snippet = (
        '  <link rel="alternate" type="application/rss+xml" '
        'title="Le Radar MapTrotter" href="/feed.xml" />\n  '
    )
    path.write_text(text[:idx] + snippet + text[idx:], encoding="utf-8")
    return True
