# DinamicaAgenti

**What it is.** A cabinet system that walks a Romanian accounting practice's *documente primare*
(e-Factura invoices, bank statements, receipts, expense reports) to SAGA C, the program that
keeps the books. It reads each document, decides which path (*cale*) it is on, checks the gate
(*poartă*) that path needs, prepares the XML SAGA imports, and reads SAGA's own reports back to
check the month before it is closed. **It never keeps books and never posts**: SAGA does, and a
person validates every posting.

**For whom.** One accountant keeping many clients' books in SAGA C.

**The line.** *Documentul primar nu ia calea fără poartă* — no document primar moves along its
path without its gate (`LAW.md`).

## How it works

Three pieces (`ARCHITECTURE.md`):

| Piece | Does | Decides |
|---|---|---|
| **Paperclip** | runs the firm: issues, people, questions, approvals, budgets, activity | who may act, and when |
| **Hankweave** | runs the steps where a model reads or classifies, one sealed codon at a time | nothing: it proposes and explains |
| **Gate kit** (`kit/`, this repo) | catalog, gates, checks, controls, SAGA XML, SAGA exports, the dossier store, the router | every route, gate and check |

Four procedures, each a kind of Paperclip issue routed by the gate kit:

```
documents (SPV zips, UBL XML, statement PDFs, expense reports)
  → Sorting        batch:{id}            what is this file, is it primary, may it emit
  → Document path  job:{id}              extract → bind → PRE → judge → person approves → package
  → SAGA C         the import agent imports the XML; a person validates (Validare)
  → Reconcile      recon:{cui}:{period}  is it already in the books / was it posted as expected
  → Month close    close:{cui}:{period}  SAGA's exports against the month's expected set → file or hold
```

## Where it stands (2026-10-07)

Design and skeleton. The repository holds the principles, the architecture, the plan, the
folder layout, the catalog rows (all `draft`) and the first pieces of the gate kit: the CUI
check digit, the catalog loader, Sorting (the emit gates), the e-invoice reader (UBL, XML
first), the dossier store (SQLite per client), PRE / POST matching with the settlement
proposal, and the period difference with the month's controls. No SAGA export reader, route or hank is written yet; no model is pinned (D3). Next:
`BUILD.md`.

## Where things are

| Path | Holds |
|---|---|
| `LAW.md` | the principles, `P1` … `P16`, with permanent ids |
| `AGENTS.md` | how an agent works here |
| `ARCHITECTURE.md` | the three pieces, the four procedures, questions, model roles, the dossier store, the firm |
| `BUILD.md` | open work packages and the proof programme |
| `RESEARCH_LOG.md` | external tools and formats, quoted from their sources with dates |
| `catalog/` | the ontology as YAML (`catalog/README.md`) |
| `kit/` | the gate kit (Python) and its CLI |
| `hanks/` | one folder per hank: `hank.json` and its role cards |
| `paperclip/` | the company set-up: roles, labels, routines, issue templates |
| `saga-agent/` | the import program for the SAGA machine (later) |
| `fixtures/`, `tests/` | invented firms and documents, SAGA test-firm exports; pytest |
| `loops/` | the SAGA C proof loops |
| `docs/design/` | the design note this repository was set up from |

## Run it

```bash
uv sync                                   # install
uv run pytest -q                          # tests
uv run ruff check . && uv run ruff format --check .
uv run kit cui RO41526372                 # check a CUI's check digit
uv run kit catalog                        # load and check the catalog
uv run kit read spv.zip --client RO41526372   # read an e-invoice (XML first), inbound or outbound
```
