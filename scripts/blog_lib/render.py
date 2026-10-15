"""Markdown → HTML body + fill article.html template with JSON-LD."""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

SITE = "https://maptrotter.xyz"

DATE_LABELS = {
    "fr": {
        "months": [
            "",
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ],
        "fmt": "{d} {month} {y}",
    },
    "en": {
        "months": [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        "fmt": "{month} {d}, {y}",
    },
    "es": {
        "months": [
            "",
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ],
        "fmt": "{d} de {month} de {y}",
    },
}


def format_date_label(iso: str, locale: str) -> str:
    d = date.fromisoformat(iso[:10])
    conf = DATE_LABELS.get(locale, DATE_LABELS["fr"])
    return conf["fmt"].format(d=d.day, month=conf["months"][d.month], y=d.year)


def markdown_to_html(md: str) -> str:
    """Lightweight Markdown subset → HTML for MapTrotter articles."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_ul = False
    in_ol = False
    in_faq = False
    direct_mode = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_direct() -> None:
        nonlocal direct_mode
        if direct_mode:
            out.append("</aside>")
            direct_mode = False

    def close_faq() -> None:
        nonlocal in_faq
        if in_faq:
            out.append("</div>")
            in_faq = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            close_lists()
            i += 1
            continue

        if stripped.startswith("```"):
            close_lists()
            close_direct()
            i += 1
            continue

        h = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if h:
            close_lists()
            close_direct()
            level = len(h.group(1))
            title = h.group(2).strip()
            # H1 is rendered by the page template — skip duplicate
            if level == 1:
                i += 1
                continue
            if level == 2 and re.match(r"(?i)^direct answer$", title):
                close_faq()
                out.append('<aside class="direct-answer">')
                direct_mode = True
                i += 1
                continue
            if level == 2 and re.match(r"(?i)^faq$", title):
                close_faq()
                out.append('<div class="article-faq">')
                out.append(f"<h2>{inline_md(title)}</h2>")
                in_faq = True
                i += 1
                continue
            if level == 2 and re.match(r"(?i)^cta$", title):
                close_faq()
                # CTA block is also in the template; keep a soft closing paragraph
                out.append(f"<h2>{inline_md(title)}</h2>")
                i += 1
                continue
            close_faq() if level == 2 else None
            tag = f"h{level}"
            out.append(f"<{tag}>{inline_md(title)}</{tag}>")
            i += 1
            continue

        # FAQ Q as **Question?**
        faq_q = re.match(r"^\*\*(.+\?)\*\*\s*$", stripped)
        if in_faq and faq_q:
            close_lists()
            question = faq_q.group(1)
            # gather answer lines until next Q or heading
            ans_lines: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt:
                    i += 1
                    if ans_lines:
                        break
                    continue
                if nxt.startswith("#") or re.match(r"^\*\*.+\?\*\*\s*$", nxt):
                    break
                ans_lines.append(nxt)
                i += 1
            answer = " ".join(ans_lines)
            out.append("<details>")
            out.append(f"<summary>{inline_md(question)}</summary>")
            out.append(f"<p>{inline_md(answer)}</p>")
            out.append("</details>")
            continue

        ul = re.match(r"^[-*]\s+(.+)$", stripped)
        if ul:
            close_direct()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline_md(ul.group(1))}</li>")
            i += 1
            continue

        ol = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol:
            close_direct()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline_md(ol.group(1))}</li>")
            i += 1
            continue

        close_lists()
        # paragraph: gather consecutive text lines
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt.startswith("#")
                or re.match(r"^[-*]\s+", nxt)
                or re.match(r"^\d+\.\s+", nxt)
                or re.match(r"^\*\*.+\?\*\*\s*$", nxt)
            ):
                break
            para.append(nxt)
            i += 1
        out.append(f"<p>{inline_md(' '.join(para))}</p>")
        if direct_mode:
            close_direct()

    close_lists()
    close_direct()
    close_faq()
    return "\n".join(out)


def inline_md(text: str) -> str:
    # escape first, then restore intentional markup via placeholders
    escaped = html.escape(text)
    escaped = re.sub(
        r"\*\*(.+?)\*\*",
        r"<strong>\1</strong>",
        escaped,
    )
    escaped = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
        r"<em>\1</em>",
        escaped,
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    return escaped


def ensure_json_ld(
    data: dict[str, Any] | list[Any] | None,
    *,
    meta: dict[str, Any],
    canonical: str,
) -> dict[str, Any]:
    """Normalize / fill defaults for BlogPosting + FAQPage (+ Place/ItemList)."""
    locale = meta.get("locale") or "fr"
    title = meta.get("title") or ""
    description = meta.get("description") or ""
    date_iso = str(meta.get("date") or date.today().isoformat())[:10]
    image = f"{SITE}/splash.png"

    graph: list[dict[str, Any]] = []
    if isinstance(data, dict) and "@graph" in data:
        graph = [g for g in data["@graph"] if isinstance(g, dict)]
    elif isinstance(data, list):
        graph = [g for g in data if isinstance(g, dict)]
    elif isinstance(data, dict):
        graph = [data]

    types = {g.get("@type") for g in graph}
    if not ({"BlogPosting", "Article"} & types):
        graph.insert(
            0,
            {
                "@type": "BlogPosting",
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
                "headline": title,
                "description": description,
                "image": image,
                "author": {"@type": "Organization", "name": "Équipe MapTrotter"},
                "publisher": {
                    "@type": "Organization",
                    "name": "MapTrotter",
                    "url": f"{SITE}/",
                    "logo": {
                        "@type": "ImageObject",
                        "url": f"{SITE}/favicon.png",
                    },
                    "parentOrganization": {"@type": "Organization", "name": "xWalk"},
                },
                "datePublished": date_iso,
                "dateModified": date_iso,
                "inLanguage": locale,
            },
        )

    # Patch BlogPosting fields (force canonical / dates to match published URL)
    for g in graph:
        if g.get("@type") in ("BlogPosting", "Article"):
            g["mainEntityOfPage"] = {"@type": "WebPage", "@id": canonical}
            g.setdefault("headline", title)
            g.setdefault("description", description)
            g.setdefault("image", image)
            g["datePublished"] = g.get("datePublished") or date_iso
            g["dateModified"] = date_iso
            g["inLanguage"] = locale
            g.setdefault(
                "publisher",
                {
                    "@type": "Organization",
                    "name": "MapTrotter",
                    "url": f"{SITE}/",
                    "parentOrganization": {"@type": "Organization", "name": "xWalk"},
                },
            )

    return {"@context": "https://schema.org", "@graph": graph}


def render_article_html(
    *,
    template: str,
    meta: dict[str, Any],
    body_html: str,
    json_ld: dict[str, Any],
) -> str:
    locale = meta.get("locale") or "fr"
    title = str(meta.get("title") or "")
    description = str(meta.get("description") or "")
    slug = str(meta.get("slug") or "")
    date_iso = str(meta.get("date") or date.today().isoformat())[:10]
    category = str(meta.get("category") or "Guides")
    reading = str(meta.get("readingMinutes") or 5)
    canonical = f"{SITE}/blog/{slug}.html"
    og = f"{SITE}/splash.png"
    date_label = format_date_label(date_iso, locale)
    json_block = json.dumps(json_ld, ensure_ascii=False, indent=2)

    html_out = template
    # Published pages must be indexable (template ships with noindex)
    html_out = html_out.replace(
        'content="noindex, follow"',
        'content="index, follow, max-snippet:-1, max-image-preview:large"',
    )
    html_out = re.sub(
        r"<html\s+lang=\"[^\"]*\"",
        f'<html lang="{html.escape(locale)}"',
        html_out,
        count=1,
    )
    # Replace JSON-LD script body
    html_out = re.sub(
        r"<script type=\"application/ld\+json\">\s*.*?\s*</script>",
        f'<script type="application/ld+json">\n{json_block}\n  </script>',
        html_out,
        count=1,
        flags=re.DOTALL,
    )

    replacements = {
        "{{TITLE}}": html.escape(title),
        "{{DESCRIPTION}}": html.escape(description),
        "{{CANONICAL}}": canonical,
        "{{DATE_ISO}}": date_iso,
        "{{DATE_LABEL}}": html.escape(date_label),
        "{{CATEGORY}}": html.escape(category),
        "{{READING_MINUTES}}": html.escape(reading),
        "{{OG_IMAGE}}": og,
        "{{BODY_HTML}}": body_html,
        "{{LANG}}": locale,
        "{{JSON_LD}}": json_block,
    }
    for key, value in replacements.items():
        html_out = html_out.replace(key, value)

    # Strip template-only HTML comment block at top of head
    html_out = re.sub(
        r"\s*<!--\s*TEMPLATE SOURCE.*?-->\s*",
        "\n  ",
        html_out,
        count=1,
        flags=re.DOTALL,
    )
    return html_out


def load_template(root: Path) -> str:
    return (root / "article.html").read_text(encoding="utf-8")
