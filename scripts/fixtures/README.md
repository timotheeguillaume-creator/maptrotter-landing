# Fixtures (no API key required)

`sample-gemini-response.md` mimics a Gemini free-tier response for local / CI dry-runs:

```bash
python3 scripts/generate-blog-post.py --dry-run \
  --fixture scripts/fixtures/sample-gemini-response.md
```

Output lands in `/tmp/maptrotter-blog-dry-run` (or `$DRY_RUN_DIR`).
