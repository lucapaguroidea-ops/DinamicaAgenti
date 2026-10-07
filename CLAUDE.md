# DinamicaAgenti — session loader

1. Read `README.md` (what, why, where it stands), `LAW.md` (the principles) and `AGENTS.md` (how
   to work) before any code.
2. Take the next WP from `BUILD.md`; one WP per commit; mark it `done` in the same commit and
   remove its details from `BUILD.md`.
3. No client data in this repo: invented CUIs must pass the check digit
   (`kit.types.cui_is_valid`).

```bash
uv sync                                   # install
uv run pytest -q                          # tests
uv run ruff check . && uv run ruff format --check .
```
