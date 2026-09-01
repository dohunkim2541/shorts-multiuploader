# Contributing

Keep changes creator-neutral and preserve the cell-level safety model.

1. Do not add real handles, profile URLs, campaign names, legal review codes,
   cookies, screenshots, or downloaded media.
2. Put creator-specific behavior in the ignored content-policy file, not Python.
3. Keep failures isolated by platform lane and require fresh verification before
   any retry that could duplicate a post.
4. Add selector candidates without removing older UI variants unless evidence
   proves they are unsafe.
5. Add or update tests and document reusable failure modes.

Run before opening a pull request:

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src
```

Live posting tests belong on private test accounts and must never run in CI.
