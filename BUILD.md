# BUILD — open work

One WP per commit; mark it `done` in the same commit and remove its details here (the commit
message keeps the what and why). Status: `todo` | `in-progress` | `parked` | `decision` (the
owner decides before any code). Test data is invented; invented CUIs pass the check digit.

## Status

| id | status | depends | title |
|---|---|---|---|
| WP-01 | done | — | Repository skeleton: docs, folder layout, `kit` package with the CUI check, tests, CI |
| WP-02 | done | — | `LAW.md` reviewed and approved by the owner (2026-10-07) |
| WP-03 | todo | WP-02 | Citation test: every `[test]` principle has a test naming it |
| WP-04 | todo | WP-02 | Catalog loader: row schemas, `status: draft`, unique ids, additive files, unknown id = error |
| WP-05 | todo | WP-04 | Catalog rows: source documents, Job kinds, articole, mouths, reconcile profiles, close kinds, controls, filings, question kinds, model roles (`ARCHITECTURE.md` §4–§6) |
| WP-06 | todo | WP-05 | Sorting in the kit: emit gates, Job kind, container split (`kit emit`) |
| WP-07 | todo | WP-04, R3 | UBL reader, XML first (P6): CIUS-RO quoted in `RESEARCH_LOG.md` first |
| WP-08 | todo | D1 | Dossier store: unique keys and append-only logs (`ARCHITECTURE.md` §7) |
| WP-09 | todo | WP-07, WP-08 | PRE / POST matching and the settlement proposal |
| WP-10 | todo | R4 | SAGA XML renderer: tags only from SAGA's manual or a test-firm import (P16) |
| WP-11 | todo | WP-08 | Period difference and controls; materiality (P11) |
| WP-12 | todo | WP-05, WP-08 | Questions: closed answer schemas, checks, the answer log (`kit answer`, P12) |
| WP-13 | todo | WP-06 … WP-12 | The router (`kit route`): the four procedures' route tables (P7) |
| WP-14 | todo | R1 confirmed, D3 | The five hanks and `kit verify` |
| WP-15 | todo | R2 confirmed, D2 | Paperclip company: roles, labels, routines, budgets, the Dispatcher |
| WP-16 | todo | WP-13 | Invented firms (five client types) and end-to-end scenarios |
| WP-17 | todo | WP-10, WP-16 | Loop 0 in a SAGA C test firm |

## Decisions (owner)

| id | Question | Options |
|---|---|---|
| D1 | Dossier store engine | SQLite per client; or one Postgres beside Paperclip's |
| D2 | How a question issue carries its answer in Paperclip | an issue document; a structured comment; an approval stage of an execution policy (R2) |
| D3 | Exact model id per role, and the harness that runs it | per role row in the catalog (P8) |
| D4 | Where Paperclip, the dossiers and the hank execution directories run, and who may read them | |
| D5 | Non-payer reverse-charge accounts: 4423 or 446x | until decided: no expected accounts, always a person |
| D6 | Receipts through an accounting note (DBF mouth) | decided after the receipts loop |

## The proof programme

Every catalog row has one state: **possible** (named, not yet run), **synthetic** (a passing
scenario drives it), **saga** (proven round-trip in a SAGA C test firm, owner-approved) or
**out** (will not be built, with the reason). A row goes `active` only from **saga** (P14).

A **loop** takes one slice — a handful of rows, one or two client types, two or three months,
10–30 documents per firm-month at first. The builder generates documents and packages; the owner
imports, validates and exports in SAGA (one session per loop); the kit reads the exports back and
makes three comparisons:

- **meaning** — generator ↔ SAGA: did SAGA book each document as meant? semantic: the owner decides;
- **reader** — SAGA's export ↔ the kit's reader: mechanical: the builder fixes it;
- **model** — simulated book ↔ SAGA: the builder fixes the generator.

New findings in a loop become one **possible** line, never work inside that loop. The SAGA C
build is pinned for a run of loops.

| Loop | Slice | Client type |
|---|---|---|
| 0 | the four XML mouths, SAGA's sample XML, import user rights, exports, backup and restore | test firm |
| 1 | RO e-Factura sales and purchases, bank settlement | VAT payer, monthly |
| 2 | bank statements: fees, transfers, unmatched lines | VAT payer |
| 3 | storno, both sides | VAT payer |
| 4 | TVA la încasare | încasare |
| 5 | expense reports, receipts with and without CUI | receipts |
| 6 | foreign invoices, reverse charge | cross-border |
| 7 | non-payer reverse charge (D5) | non-payer |
| 8 | payroll (evidence only, keyed) | VAT payer |
| 9 | close and filings across a quarter | all five |

## The evidence ledger

Per client-month, from stored data only (dossier logs, Paperclip activity, hank journals):

- **Friction:** questions asked; asked again; proposals changed or refused; documents held for a person.
- **Control:** stopped at a gate; controls failed then passed; caught late by POST; reopened after acked.
- **Not measured:** minutes per question; errors found after a filing; cost per call where only per-key spend is reported.

A gate always approved unchanged that never stopped anything is friction with no control; a gate
that stopped a real error is control until a cheaper design gives the same control (P15).
