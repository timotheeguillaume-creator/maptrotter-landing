#!/usr/bin/env python3
"""Unit checks for JSON-LD salvage + gate tolerances (no API)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blog_lib import gates, parse, render  # noqa: E402


SAMPLE = (ROOT / "scripts" / "fixtures" / "sample-gemini-response.md").read_text(
    encoding="utf-8"
)


class ParseSalvageTests(unittest.TestCase):
    def test_extract_standard_fence(self):
        _, body = parse.parse_frontmatter(SAMPLE)
        cleaned, data = parse.extract_json_ld(body)
        self.assertIsNotNone(data)
        self.assertIn("Direct Answer", cleaned)
        self.assertNotIn("```json-ld", cleaned)

    def test_extract_jsonld_alias(self):
        blob = 'Hello\n```jsonld\n{"@type": "BlogPosting"}\n```\n'
        cleaned, data = parse.extract_json_ld(blob)
        self.assertEqual(data, {"@type": "BlogPosting"})
        self.assertEqual(cleaned.strip(), "Hello")

    def test_extract_script_tag(self):
        blob = 'Body\n<script type="application/ld+json">{"@type":"FAQPage"}</script>\n'
        cleaned, data = parse.extract_json_ld(blob)
        self.assertEqual(data, {"@type": "FAQPage"})
        self.assertIn("Body", cleaned)

    def test_bare_trailing_json(self):
        blob = (
            "# Title\n\n## FAQ\n\n"
            '{"@context":"https://schema.org","@graph":[{"@type":"BlogPosting"}]}'
        )
        cleaned, data = parse.extract_json_ld(blob)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["@context"], "https://schema.org")


class JsonLdSynthTests(unittest.TestCase):
    def test_synthesize_missing_faq_and_blog(self):
        _, body = parse.parse_frontmatter(SAMPLE)
        cleaned, _ = parse.extract_json_ld(body)
        meta = {
            "title": "Cafés Lyon",
            "description": "desc",
            "locale": "fr",
            "date": "2026-10-16",
            "city": "Lyon",
            "slug": "cafes-lyon",
        }
        out = render.ensure_json_ld(
            None,
            meta=meta,
            canonical="https://maptrotter.xyz/blog/cafes-lyon.html",
            markdown=cleaned,
        )
        types = {g.get("@type") for g in out["@graph"]}
        self.assertIn("BlogPosting", types)
        self.assertIn("FAQPage", types)
        self.assertIn("Place", types)
        faq = next(g for g in out["@graph"] if g["@type"] == "FAQPage")
        self.assertGreaterEqual(len(faq["mainEntity"]), 3)

    def test_gates_pass_after_synth(self):
        meta, body = parse.parse_frontmatter(SAMPLE)
        cleaned, _ = parse.extract_json_ld(body)
        meta["phrase"] = "cafés lyon"
        meta.setdefault("slug", "cafes-rencontrer-locaux-lyon")
        ld = render.ensure_json_ld(
            None,
            meta=meta,
            canonical="https://maptrotter.xyz/blog/cafes-rencontrer-locaux-lyon.html",
            markdown=cleaned,
        )
        result = gates.run_gates(meta, cleaned, ld, recent_titles=[], recent_bodies=[])
        # Fixture may be short; drop length only
        result.failures = [f for f in result.failures if not f.startswith("too short:")]
        result.ok = len(result.failures) == 0
        self.assertTrue(result.ok, result.failures)


class GateToleranceTests(unittest.TestCase):
    def test_direct_answer_soft_band(self):
        # 28 words — old hard floor was 30; new floor 25
        words = " ".join(["word"] * 28)
        body = (
            "# Title\n\n## Direct Answer\n\n"
            + words
            + "\n\n## A\n\nx\n\n## B\n\nx\n\n## C\n\nx\n\n## FAQ\n\n"
            "**Q1?**\nA1\n\n**Q2?**\nA2\n\n**Q3?**\nA3\n\n"
            "## CTA\n[MapTrotter](/) MapTrotter again\n"
        )
        # Pad to 600+ words for length gate
        body += "\n\n" + " ".join(["contenu"] * 600)
        meta = {
            "title": "Title MapTrotter",
            "slug": "title-maptrotter",
            "locale": "fr",
            "phrase": "unused-phrase-xyz",
        }
        ld = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "BlogPosting"},
                {"@type": "FAQPage", "mainEntity": [{}, {}, {}]},
            ],
        }
        result = gates.run_gates(meta, body, ld)
        da_fails = [f for f in result.failures if "Direct Answer word count" in f]
        self.assertEqual(da_fails, [], result.failures)


def _load_generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_blog_post",
        ROOT / "scripts" / "generate-blog-post.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GenerateRetryTests(unittest.TestCase):
    def test_fixture_dry_run_ok(self):
        mod = _load_generator()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                "os.environ",
                {"DRY_RUN": "1", "DRY_RUN_DIR": tmp, "GATE_ATTEMPTS": "3"},
            ):
                argv = [
                    "generate-blog-post.py",
                    "--dry-run",
                    "--fixture",
                    str(ROOT / "scripts" / "fixtures" / "sample-gemini-response.md"),
                    "--slug-override",
                    "test-fixture-gate-retry",
                ]
                with mock.patch.object(sys, "argv", argv):
                    rc = mod.main()
                self.assertEqual(rc, 0)

    def test_missing_jsonld_salvaged_without_regen(self):
        mod = _load_generator()
        meta, body = parse.parse_frontmatter(SAMPLE)
        cleaned, _ = parse.extract_json_ld(body)
        lines = ["---"]
        for k, v in meta.items():
            if isinstance(v, list):
                items = ", ".join(f'"{x}"' for x in v)
                lines.append(f"{k}: [{items}]")
            elif isinstance(v, str):
                lines.append(f'{k}: "{v}"')
            else:
                lines.append(f"{k}: {v}")
        lines.append("---")
        stripped = "\n".join(lines) + "\n\n" + cleaned + "\n"

        with tempfile.TemporaryDirectory() as tmp:
            fix = Path(tmp) / "no-ld.md"
            fix.write_text(stripped, encoding="utf-8")
            out = Path(tmp) / "out"
            out.mkdir()
            with mock.patch.dict(
                "os.environ",
                {"DRY_RUN": "1", "DRY_RUN_DIR": str(out), "GATE_ATTEMPTS": "1"},
            ):
                argv = [
                    "generate-blog-post.py",
                    "--dry-run",
                    "--fixture",
                    str(fix),
                    "--slug-override",
                    "test-salvage-jsonld",
                    "--allow-short-fixture",
                ]
                with mock.patch.object(sys, "argv", argv):
                    rc = mod.main()
                self.assertEqual(rc, 0, "missing json-ld should be salvaged")
                html = out / "blog" / "test-salvage-jsonld.html"
                self.assertTrue(html.exists())
                self.assertIn("FAQPage", html.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
