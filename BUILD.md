# BUILD — open work

One WP per commit; mark it `done` in the same commit and remove its details here (the commit
message keeps the what and why). Status: `todo` | `in-progress` | `parked` | `decision` (the
owner decides before any code). Test data is invented; invented CUIs pass the check digit.

## Status

| id | status | depends | title |
|---|---|---|---|
| WP-01 | done | — | Repository skeleton: docs, folder layout, `kit` package with the CUI check, tests, CI |
| WP-02 | done | — | `LAW.md` reviewed and approved by the owner (2026-10-07) |
| WP-03 | done | WP-02 | Citation test: every `[test]` principle has a test naming it |
| WP-04 | done | WP-02 | Catalog loader: row schemas, `status: draft`, unique ids, additive files, unknown id = error |
| WP-05 | done | WP-04 | Catalog rows: source documents, Job kinds, articole, mouths, reconcile profiles, close kinds, controls, filings, question kinds, model roles (`ARCHITECTURE.md` §4–§6) |
| WP-06 | done | WP-05 | Sorting in the kit: emit gates, Job kind, container split (`kit emit`) |
| WP-07 | done | WP-04, R3 | UBL reader, XML first (P6): CIUS-RO quoted in `RESEARCH_LOG.md` first |
| WP-08 | done | WP-04 | Dossier store: unique keys and append-only logs (`ARCHITECTURE.md` §7) |
| WP-09 | done | WP-07, WP-08 | PRE / POST matching and the settlement proposal |
| WP-10 | todo | R4 | SAGA XML renderer: tags only from SAGA's manual or a test-firm import (P16) |
| WP-11 | done | WP-08 | Period difference and controls; materiality (P11) |
| WP-12 | done | WP-05, WP-08 | Questions: closed answer schemas, checks, the answer log (`kit answer`, P12) |
| WP-13 | done | WP-06 … WP-12 | The router (`kit route`): the four procedures' route tables (P7) |
| WP-14 | done | R1 confirmed | The five hanks and `kit verify`; every role refuses until D3 |
| WP-15 | done | R2 confirmed, D2 | Paperclip company: roles, labels, routines, budgets, the Dispatcher |
| WP-16 | done | WP-13 | Invented firms (five client types) and end-to-end scenarios |
| WP-17 | todo | WP-10, WP-16 | Loop 0 in a SAGA C test firm |
| WP-19 | todo | R4 | SAGA export reader: registru jurnal, balanță, purchase / sales journals → a books export (`kit dossier add-export` reads SAGA's files, not the kit's JSON) |
| WP-20 | in-progress | D9 | Pin the shared core (PoartaContabila `poarta_contabila.core`, `pyproject.toml` at commit `a257986`, `CORE_VERSION` 0.4.0, which holds PoartaContabila WP-87 and WP-88) and replace the kit's re-implementations one module per WP, each with a parity test, then delete it: `ubl.py`, `catalog.py`, `recon.py`, `period.py`, `sorting.py`, `synthetic.py`, `questions.py` (module review, owner 2026-10-14, Q-9, Q-13). The pin is a commit because tags cannot be pushed from the build sessions: cutting `core-v0.4.0` on it is the owner's, and the pin then moves to the tag. Cost: until the core is extracted (Q-13, "inside PC, extract later") the pin pulls PoartaContabila's runtime packages into the lockfile (from 20 to 79 packages), though importing the core loads no graph, HTTP, database or model client (the parity test checks). Step 1 done: the pin and `tests/test_core_parity.py` (both readers agree on every field they share over exactly 390 synthetic invoices; one declared gap, with the core's refusal reason, waits on D9). Open gap for the `catalog.py` step: the kit's CO.DiT vocabulary (`catalog/10_law_firm/axes.yaml`) differs from the core's (`ArticoleCoDitAxes`): the kit lacks `tva_period`, `d100_period`, `d112_period` (so `kit dossier set-codit` cannot set them); `exig` is `tva_la_livrare` in the kit, `tva_exig_livrare` in the core; `impozit` `micro_3`, `norma_venit` and `forma` `ii` are the kit's only. Until `catalog.py` is replaced, the calendar (WP-21) holds a dossier whose CO.DiT is outside the core's vocabulary, and names the axis and value. Step `synthetic.py`: not replaced, the module waits on the owner. The two modules share a purpose, not a shape: the kit's `month` draws `GenDoc`s (bytes) and `simulated_book` returns a `kit.recon.Witness` that `kit/scenario.py` hands to `period_diff` (callers: `kit/scenario.py`, `kit/cli.py`, `tests/test_month.py`, `tests/test_scenarios.py`); the core's `months.month` / `realistic` draw `Invoice` / `Statement` / `ExpenseReport` / `Bon` / `Payroll` objects and a `Book` of `Entry` lines and SAGA / NextUp exports. `tests/test_synthetic_parity.py` holds what agrees (the same five firm keys and names; every axis but `exig`; on 360 of the core's RO invoices over a quarter both books post the same partner and VAT accounts and amounts, and the same total to the rest; this proves account and side selection and the total to the rest, while the amounts agree largely by construction, since the kit is fed the core's net and VAT and its own VAT-rate drawing is not compared; the other 30 are excluded: 20 credit notes, which the kit never draws (gap 5), and 10 foreign purchases, which the kit's book refuses (gap 9)) and declares nine gaps, (kit, core): (1) `firm_cuis`: every firm's CUI differs (both invented, both valid); (2) `firm_folders`: `ALFA`… vs `0001`…; (3) `exig_axis`: `tva_la_livrare` vs `tva_exig_livrare`, and the non-payer has `exig` in the kit and none in the core; (4) `partners`: 2 suppliers, 2 customers, 1 foreign in the kit vs 4 suppliers (one not a VAT payer), 3 customers, 2 foreign suppliers, 1 foreign customer in the core, none shared; (5) `month_shape`: kinds `purchase` / `sale` / `foreign_sale` / `foreign_purchase` / `decont` vs the core's document types (credit notes, bank statements, receipts, payroll, named defects are the core's only); not comparable by seed; (6) `kit_invoices_without_vat_breakdown`: the kit writes no `cac:TaxSubtotal`, so the core's reader refuses all 99 kit invoices of the quarter: the 81 with VAT with "VAT subtotals do not sum to TaxAmount", the 18 with zero VAT with "VAT subtotals [] do not match line categories"; D9 decides this gap, it is not a separate decision; (7) `cost_and_revenue_accounts`: the kit posts every net to 628 / 704, the core to each item's account (604, 611, 612, 624, 626, 628, 704, 707); (8) `partner_accounts`: the kit posts to 401 / 4111, the core to analytics (401.0000n, 4111.0000n); (9) `foreign_purchase_posting`: the core's 10 foreign purchases in EUR of the quarter (7 for `abroad`, 3 for `neplatitor`): the kit's book refuses every one (`to_person`) and posts nothing, the core's posts `abroad`'s as 628 / 401 and 4426 / 4427, `neplatitor`'s as 628 / 401 (debit / credit); D5 decides this gap, it is not a separate decision. |
| WP-21 | done | WP-20, PoartaContabila WP-87 | The calendar in the firm: a routine opens `calendar:{cui}:{period}`; the pinned core dates, refuses or defers each owed filing; the Dispatcher holds a calendar that refuses or whose register is not fresh (P10) |
| WP-18 | done | WP-15 | Sources and books exports in the dossier; every kit step an executor of the Dispatcher; `kit hank-run` (render, input, run, `kit verify`) |

## Decisions (owner)

| id | Question | Options |
|---|---|---|
| D3 | Exact model id per role, and the harness that runs it | `model:` on each of the 9 rows of `catalog/50_control/model_roles.yaml` (P8); until then every hank refuses and a person is asked |
| D4 | Where Paperclip, the dossiers and the hank execution directories run, and who may read them | the Paperclip deployment (`authenticated`, not `local_trusted`, for more than one person); `KIT_HOME`, `DOSSIERS`, `ACCOUNTANT_USER_ID`, `SAGA_AGENT_URL`; where a webhook secret is kept; the budgets and the close date marked `owner` in `paperclip/company.yaml` |
| D5 | Non-payer reverse-charge accounts: 4423 or 446x | until decided: no expected accounts, always a person |
| D6 | Receipts through an accounting note (DBF mouth) | decided after the receipts loop |
| D7 | Which routes may carry client data to a model, and where hanks run (the module review's F17; Q-12) | a principle in `LAW.md`, the owner's dated change |
| D8 | Payroll as evidence only, in `LAW.md`, as PoartaContabila's L17 (Q-19) | a principle in `LAW.md`, the owner's dated change |
| D9 | The shared core's UBL reader: an invoice without a VAT breakdown (`cac:TaxSubtotal`) is accepted by the kit and refused by the core (`tests/test_core_parity.py`). Which rule does the core keep, and does `for_client` / `is_storno` / `customization_id` move into it? | the core's (stricter) rule, with the kit's extras added to the core; or the kit's rule in the core; until decided `kit/ubl.py` stays |

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
