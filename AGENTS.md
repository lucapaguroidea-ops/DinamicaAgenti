# AGENTS.md — how an agent works here

This repository is the only source of truth: `README.md` (what and why), `LAW.md` (the
principles, `P<n>`), this file (how), `BUILD.md` (what next), `ARCHITECTURE.md` (the machine),
`catalog/` (the ontology), `RESEARCH_LOG.md` (external formats, quoted).

## Before any code

1. Read `README.md`, `LAW.md`, this file, then the part of `ARCHITECTURE.md` and the catalog file
   you will touch.
2. Read `BUILD.md`. Take the first work package whose status is `todo` and whose `depends` are
   done.
3. Stop and ask the owner when the WP is a `decision`, when a change touches a principle, or when
   it adds, removes or relaxes a gate (P15). Do not invent the answer.

## Operating loop

```
restate the change as: articol + poartă open/closed
write or extend a failing test named in the WP
smallest change that passes
uv run pytest -q; uv run ruff check . && uv run ruff format --check .
one WP per commit: mark it done in BUILD.md and remove its details there
```

## Hard bans

- No model on a route (P7). The Dispatcher runs `kit route`; it has no model.
- No model call outside a role row of the catalog, or with a model id the row does not pin (P8).
- No hank that decides: no gate, no mouth, no VAT treatment, no file or hold. A hank writes a
  proposal file; the kit checks it.
- No agent answers a question meant for a person; no agent posts, validates or closes a month in
  SAGA (P5).
- No store keeps books: no journal, no chart of accounts, no trial balance as books (P4).
- No write to SAGA's database (P3).
- No invented SAGA XML tag, export layout or tool setting: quote it in `RESEARCH_LOG.md` with
  its date, or prove it in a test firm (P16).
- No `status: active` on a catalog row before it is proven in SAGA C and the owner approves (P14).
- No client data in this repository: invented firms only; invented CUIs pass
  `kit.types.cui_is_valid`.
- No declaration built by this system: SAGA produces it; a filing closes on its receipt.

## Where to put new work

| Kind of change | Where |
|---|---|
| A new walk on a document (articol de cale) | `catalog/30_path/` |
| A new file type or emit rule | `catalog/20_document/` |
| A new SAGA mouth | `catalog/30_path/` mouths file + a test-firm fixture |
| A new question kind | `catalog/50_control/` — a gate: the owner decides (P15) |
| A new close control | `catalog/60_practice/` — a gate: the owner decides (P15) |
| A new model role | `catalog/50_control/` + its role card in `hanks/<hank>/prompts/` |
| A deterministic check or route | `kit/` |
| A model step | `hanks/` |
| A Paperclip role, label or routine | `paperclip/` |

A new catalog row enters as `status: draft` (P14).
