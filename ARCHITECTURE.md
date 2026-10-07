# Architecture

The machine as designed on 2026-10-07 (`docs/design/`). `LAW.md` is the law (cited `P<n>`). What
is built and what is not is tracked in `BUILD.md`.

## 1. Shape

```
client documents ──► Paperclip issue (batch / job)
                         │  Dispatcher (Process adapter, no model): kit route
                         ├─► kit command (deterministic step)           ─┐
                         ├─► hank run (model step) → JSON → kit verify   ├─► dossier store (facts)
                         └─► question issue → person answers → kit answer ┘
                                              │
                                outbox XML ──► SAGA import agent → Import → person: Validare
                                SAGA exports ◄── eye: registru jurnal, balanță, journals
```

## 2. The three pieces

### Paperclip — the firm and the router

Control plane (MIT; Node.js server, React board, embedded Postgres). Used for: companies and
goals, a mixed human-and-agent org chart, issues with parent links and blocker dependencies,
atomic checkout with execution locks, execution policies with review and approval stages,
heartbeats, routines, budgets with hard stops, secrets by reference, the activity log. Agents
attach by adapter; this system uses **Process** (the Dispatcher) and **HTTP** (the SAGA import
agent). Facts about Paperclip: `RESEARCH_LOG.md` R2.

Every unit of work is an issue. Every question to a person is an issue assigned to that person.
The **Dispatcher** runs `kit route <issue>` after every event and acts on its answer.

### Hankweave — the model steps

Runtime (Apache-2.0, TypeScript). A hank (`hank.json`) is a declared sequence of codons, each one
sealed agent run with a pinned `model`, a prompt file, `continuationMode: "fresh"`,
`checkpointedFiles` and a `budget`; rigs prepare the workspace; loops repeat codons up to a
`terminateOn` limit; input is mounted read-only; every codon boundary is a git checkpoint; every
tool call goes to the event journal. Facts: `RESEARCH_LOG.md` R1.

A hank runs only where a model works, is short, ends by writing a JSON file, and decides nothing.

### The gate kit — the deterministic core (`kit/`)

A Python package and CLI. It loads the catalog, matches articole, runs every gate, check and
control, renders SAGA XML, reads SAGA's exports, computes the month's differences, validates
every answer and writes the dossier store. It is the only writer of facts and the only thing that
decides a route (P7).

| | Paperclip | Hankweave | Gate kit |
|---|---|---|---|
| Holds | issues, people, approvals, activity, budgets | hank runs: checkpoints, journal, output files | catalog, gates, controls, dossier store |
| Decides | who may act, and when | nothing: proposes and explains | every route, gate and check |
| Models | none in the router | pinned per codon, by role | none |
| People | answer, approve, sign | — | validates each answer before it counts |

## 3. Graph concepts on the new tools

The procedures are designed as state graphs. Each graph concept maps to one thing here:

| Graph concept | Here |
|---|---|
| Procedure | an issue kind + its route table in `kit/route`: `batch`, `job`, `recon`, `close` |
| Run id (`batch:` `job:` `recon:` `close:`) | the issue key, in its title and a label; one issue per key; execution lock = one run at a time; kinds never mix |
| Deterministic node | a `kit` command, run by the Dispatcher or in a hank's rig |
| Node with a model | one codon in a hank; output checked by `kit verify` before it is a fact |
| Conditional edge | `kit route` reading the dossier's facts; no model |
| Interrupt | a question issue (child of the work issue, which it blocks), assigned to the actor, the question as a JSON document |
| Resume | `kit answer` validates the answer (closed schema + the kind's check): valid → recorded, question closed, work unblocked; invalid → asked again with the error as a comment |
| Re-entering a node | each step is a fresh command or hank run; it reads the dossier, finds its answer if one exists, and only then does its side effect, behind a unique key |
| Checkpointer | dossier store (state) + Hankweave checkpoints (a model step's files) + Paperclip history |
| Glue between procedures | parent / blocker links between issues and ids in the dossier; a procedure never runs another inside itself |
| Shadow model call | a hank run whose output is recorded but read by no route |

## 4. The four procedures

**kit** = gate kit, **hank** = Hankweave, **Q** = a question to a person.

### 4.1 Sorting — `batch:{id}`

1. **Gate (kit).** Unknown file kind → Q `define_class`. A fiscal receipt whose CUI-on-document
   is not settled → Q `bon_cui_unclear`. Then the emit gates.
2. **Split (hank + Q).** A container (expense report) never becomes a Job. Once its identity and
   primary gates pass, hank `split-container` proposes parts; Q `decont_split` confirms them; each
   part is a child file through the emit gates. A part with its invoice XML is a UBL, never a PDF.
3. **Emit (kit).** One Job per file, unique on (client CUI, source hash); the Dispatcher opens
   `job:{id}`.

Emit gates (all failures listed; emit only when none):

| Gate | Fails when |
|---|---|
| class | the source-document row is not posting-eligible |
| primary | none of the row's required primary kinds is present and incomplete emit is not allowed |
| identity | the client must be on the document and is not; or a required counterparty CUI is missing or fails its check digit |
| bon fork | a fiscal receipt and nobody has said whether the client's CUI is on it |
| emit rule | not eligible; or a PDF of an RO e-invoice; or unknown; or a statement without the client's identity |
| job kind | not exactly one Job kind lists this source document (a credit note → the storno kind only) |

| Source document | What | Emits | Job kind |
|---|---|---|---|
| `ro_efactura_ubl` | RO e-invoice, CIUS-RO UBL / SPV zip | yes | `ro_efactura` / `storno` |
| `ro_efactura_pdf` | PDF of an RO e-invoice | no: waits for its XML | — |
| `foreign_invoice`, `foreign_invoice_xml` | foreign invoice, scan or UBL | yes | `foreign_invoice` |
| `bon_fiscal` | fiscal receipt | yes | `bon` |
| `extras`, `extras_pdf` | bank statement | yes, client on the document | `extras` |
| `extras_statement_pdf` | one movement line of a statement | yes, one Job per line | `extras_line` |
| `decont_cheltuieli` | expense report (container) | never: split | — |
| SAGA exports, SPV register, payroll, workings | evidence and the eye | never | — |

### 4.2 Document path — `job:{id}`

Status moves forward only: `ingested → bound → reconcile_pre → approved → packaged →
wait_validare → acked`; or ends `already_in_sink`, `rejected`, `needs_human`, `reopened`.

1. **Extract.** XML first (P6): UBL parsed, totals checked, fail closed. A scan or statement PDF
   → hank `read-document`; `kit verify` checks it: every statement line ties (opening − debits +
   credits = closing) and the holder CUI is the client's. Not confirmed → run once more with the
   strong tier, then refused and never stored.
2. **Bind (kit).** Articol rows of this procedure match on fiscal class, our role, storno, date
   validity and the client's CO.DiT axes (require / forbid). Ties: more filters, then narrower
   require, then latest `valid_from`. One → bound; none or several → Q `define_articol`.
3. **PRE (kit).** Against SAGA's registru jurnal and the SPV register: `already_posted` →
   `already_in_sink`; `absent` → continue; otherwise `needs_human` and the month's Reconcile takes
   the question.
4. **Judge (hank).** `judge-document` → `{accounts_ok, risk, needs_human}`; an error or bad answer
   → `{accounts_ok: false, risk: unknown, needs_human: true}`. Stored before the next step.
5. **Approve (Q `v3_approve`).** When `needs_human`, `accounts_ok` is not true, or the articol's
   policy says so (`always`; `first_n` per client; `never_if_risk_low`). Carries the document, the
   verdict, an explanation and, for a bank line with no partner, the kit's settlement proposal.
   Answers: `approve` | `reject` | `edit` (a patch that must still validate).
6. **Package (kit).** Refused to `needs_human` when the client's book is not SAGA; not exactly one
   mouth fits the document class; a blocking pre-package control fails; or the period has a
   filing receipt. Else the XML is written once under `export_key = module:job:schema_version` to
   the outbox.
7. **Wait for Validare (Q `wait_validare`, to the SAGA agent).** Backup label, import in Nr.+data
   sync mode, a person validates. The agent answers `{validated, saga_doc_key}`; accepted only
   when SAGA's snapshot shows that key validated. Not validated → `reopened`.
8. **Intent check (kit).** Posted document vs package: side, gross, net, VAT (where SAGA shows
   them), partner CUI. Equal → `acked`; any difference or nothing shown → `needs_human`.

| Articol (examples) | Approval policy |
|---|---|
| RO e-invoice inbound / outbound | `first_n: 5`, then by risk |
| bank statement line | `first_n: 3`, then by risk |
| foreign invoice, reverse charge, receipts, storno | `always` |

### 4.3 Reconcile — `recon:{cui}:{period}`

A loop: check the window, ask one question, apply, check again, until nothing waits.

1. **Window (kit).** Every Job stopped at PRE is checked again against the books as they are now.
   A decisive verdict goes back to its Job unless hank `review-match` contests it (it may only
   confirm, contest or abstain; never flip to posted).
2. **POST (kit).** For each acked Job: SAGA's journal lines of that posting vs the articol's
   expected accounts (by prefix; all or at least one per the profile), then amounts: 401 / 4111
   vs gross, 4426 / 4427 / 4428 vs VAT, within tolerance → `how_ok` | `how_mismatch` | need export.
3. **One question at a time:** `need_rj_export` → `recon_review_contest` → `recon_ambiguous`
   (oldest first) → `recon_how_mismatch`. Stored before asked.
4. **Apply (kit).** Verdict stored once per (Job, stage, snapshot) and handed back:
   `already_posted` → `already_in_sink`; `absent` → the Job continues at Judge.

| PRE rule | Value |
|---|---|
| keys | number and date; gross within 0.05; no conflicting partner CUI |
| number levels | `exact` (trimmed, upper) → `alnum` → `digits_core` (only with the same partner CUI) |
| already_posted | one sink document agrees on every key, or the SPV register lists it posted |
| ambiguous | two hits; two of number / date / gross agree; or no single profile |
| absent | only when every month from the document's to the Job's is covered and nothing is close |

Matching is generous on purpose: a missed match packages a duplicate; a false "close" costs one
question.

### 4.4 Month close — `close:{cui}:{period}`

A close run, never a Job. Blocked by the month's Reconcile issue while a PRE question is open.

1. **Lock (kit).** Hash of the month's Jobs (id, status, gross; rejected left out), once. A later
   different set = lock mismatch (material). Close kind from CO.DiT (standard / TVA la încasare);
   none fits = blocker.
2. **Period difference (kit).** Each SAGA document → `expected` (by SAGA key, else side + number +
   date + gross) | `explained_sink_only` (a rule) | `unexplained`. Expected Jobs not acked or
   already in the books = outbound holes. Watched accounts compared turnover for turnover. Then
   every control.
3. **Suggestion (hank).** `close-suggest` may suggest an action; it never clears material.
4. **Q `v2_close`.** `file` | `hold` | `patch_maps` | `reopen` (+ explained rule). `file` refused
   while material; `reopen` releases the lock.
5. **After file, Q `v4_codit`.** `accept` xor `skip`; accept may patch only allowed axes (auto,
   SAF-T, exig) and seed next month's (tax, VAT); never overwrites an existing next CO.DiT.
6. **Filings.** One item per declaration the CO.DiT requires, gated by its controls; SAGA
   produces the declaration; an item closes only with a receipt (Q `filing_receipt`). A period
   with a receipt gets no new package.

**Material** if: a month not covered by a books export; an outbound hole; an unexplained
document; a watched-account difference ≥ 0.01; a blocking control failed; a lock mismatch; a PRE
question open. **Watched accounts:** 401, 4111, 4426, 4427, 4428, 5121, 5311.

| Control | Severity | Rule |
|---|---|---|
| C0 synthetic parity | blocking | for each watched account, \|expected + explained − SAGA\| < 0.01 |
| C1 outbound complete | blocking | every expected Job acked, in the books, or a listed hole |
| C2 unexplained empty | blocking | no unexplained SAGA document |
| M1.1 payables tie | blocking | Σ analytics under 401 = 401, once client maps exist |
| M1.2 receivables tie | blocking | Σ analytics under 4111 = 4111, once client maps exist |
| M1.8 4428 open | blocking | Σ 4428 on open TVA-la-încasare documents = balance of 4428 |
| T regime 4428 | blocking | not a VAT payer: unexplained 4428 is material |
| M1.1 / M1.2 extended | advisory | analytics of 403–409 and 411–419 tie to their parent |
| M1.9 4424 | advisory | 4424 movement has an explained rule or expected settlement |
| T regime 442x | advisory | not a VAT payer: unexplained 4423 / 4424 goes to a person |
| C2 waiting for XML | advisory | an unexplained document matching a part waiting for its SPV XML is named |
| P duplicate | blocking, pre-package | PRE not already_posted; source hash unique |
| P hard failures | blocking, pre-package | no blocking failure before a package |

A blocking control that cannot be computed for want of an input fails; INFO only when it does not
apply.

### 4.5 Undoing, SAGA's way

| SAGA shows | In SAGA | In the system |
|---|---|---|
| imported, not validated | Anulează importul | Job rejected |
| validated, not filed | Devalidare, by a person | Job reopened, packaged again |
| in SPV or with a receipt | Stornare | a new storno Job linked to the original |
| something went badly wrong | restore of a labelled backup, by a person | runbook; never automatic |

## 5. Questions to a person

Each kind is a catalog row: actor, closed answer schema, check. In Paperclip: a child issue
assigned to the actor, labelled `q:<kind>`, the answer as a JSON document.

| Kind | Procedure | Answer | Effect |
|---|---|---|---|
| `define_class` | Sorting | `source_doc_id` (known, not unknown) | reclassified, gated again |
| `bon_cui_unclear` | Sorting | `cu_cui` xor `fara_cui` | receipt fork settled |
| `decont_split` | Sorting | `parts[]`: hash, source_doc_id, kinds | one child per part |
| `define_articol` | Document path | `articol_id` among candidates | bound |
| `v3_approve` | Document path | `approve` \| `reject` \| `edit` (+ patch) | approved / rejected / patched |
| `wait_validare` | Document path (SAGA agent) | `validated`, `saga_doc_key` | intent check / reopened |
| `need_rj_export` | Reconcile | `export_id` of the latest books export covering the months | window rechecked |
| `recon_ambiguous` | Reconcile | `already_posted` (+ sink lines) \| `override_absent` | verdict to the Job |
| `recon_review_contest` | Reconcile | `already_posted` \| `override_absent` | verdict to the Job |
| `recon_how_mismatch` | Reconcile | `ack_mismatch` xor `open_storno` | POST settled / open for storno |
| `v2_close` | Month close | `file` \| `hold` \| `patch_maps` \| `reopen` (+ rule) | filed / hold / reopened |
| `v4_codit` | Month close | `accept` xor `skip` (+ `edit`, `seed_next`) | CO.DiT patched / seeded |
| `explained_rule` | Month close | `rule_id` | rule active for the client |
| `control_disposition` | Month close | `explained_rule` \| `reopen` \| `hold` | failed control disposed |
| `filing_receipt` | Month close | `filing_id`, receipt, `submitted_by` | filing item closed |

Every answer goes to the client's answer log (P12): who, when, question hash, what was proposed,
what was chosen, outcome (`accepted` | `asked_again` | `no_question`).

## 6. Model roles and hanks

| System | Does | Never |
|---|---|---|
| System One (classifier) | classifies into closed JSON answers: judge, review a match, suggest a close action | explain to a person, write to SAGA, set CO.DiT, choose the mouth, open a gate alone |
| System Two (explainer) | explains a question; drafts text a person approves; output `{explanation, facts_cited, missing}` | post, decide a gate, answer a question, run on a route |
| Reader | reads a scan or statement PDF with no XML or text layer; copies only what is printed, every value a string | read XML, skip the kit's checks, emit, classify |

A role pins one exact model (no alias, no auto-router, no fallback list). Its role card is the
codon's prompt file; the card's hash is recorded with every call and is part of the cache key.

| Hank | System | Codons (each fresh; output a JSON file `kit verify` checks) |
|---|---|---|
| `read-document` | Reader | read header and tables → `read.json`; re-run once with the strong tier if not confirmed |
| `split-container` | Reader | propose parts → `parts.json`; a person confirms (`decont_split`) |
| `judge-document` | One + Two | judge → `verdict.json`; explain the approval question → `explain.json` |
| `review-match` | One | confirm / contest / abstain on PRE → `review.json` |
| `close-suggest` | One + Two | suggest → `suggest.json`; explain; draft a rule if unexplained documents remain |

Each hank mounts its inputs read-only, writes only to its execution directory, has a `budget`
per codon, and is run with `--max-cost` and `--max-time`. A hank never touches the dossier store.

## 7. The dossier store

One dossier per client, written only by the gate kit; outside this repository.

Engine: **SQLite, one `store.db` per client** (owner, 2026-10-07, D1). The client boundary is the
folder `dossiers/{cui}/`: records and files live behind the same boundary, a backup or restore
touches one client only, and the only way in is a function that checks the CUI and opens that
client's file. Every record still carries the CUI and is refused on a mismatch (P13).

```
dossiers/{cui}/
  store.db                  unique keys and append-only logs
  sources/{period}/…        documents as received, named by source hash
  extracts/{source_hash}/   markdown.md, tables.json, meta.json (one per backend)
  outbox/{period}/…         XML packages in SAGA's file names, one import folder per pull
  eye/{period}/…            SAGA exports: registru jurnal, balanță, purchase / sales journals
  runs/{issue}/             each hank run's output files and journal, with its checkpoints
```

| Record | Unique key | On a second write |
|---|---|---|
| Job | (client CUI, source hash) | returns the existing Job |
| Package | `module:job:schema_version` | written once |
| PRE / POST verdict | (job, stage, books snapshot) | returns the first verdict |
| Model answer | (role, input hash, card hash) | reused, never paid twice |
| Question answer | (issue, question hash) | same answer, same state |
| Close lock | (client CUI, period) | one expected-set hash |
| Control run | (CUI, period, control, snapshot) | stored once |
| Filing item | (CUI, period, filing) | closed by a receipt only |
| Backup label | `{cui}:{folder}:{utc}` | a restore of another client is refused |

## 8. The firm in Paperclip

| Role | Who | Does |
|---|---|---|
| Board | the owner | approves hires, rows going active, gate changes, test-firm evidence, budgets |
| Accountant(s) | people | upload a month; answer questions; validate in SAGA; sign the close |
| Dispatcher | agent, Process adapter, no model | `kit route` on every event; creates, blocks, unblocks, closes issues; starts hanks |
| Reader, Classifier, Explainer | agents running hanks | run their hank when assigned; budget per role |
| SAGA import agent | program on the SAGA machine (HTTP adapter), a person until built | pull outbox, backup label, import, snapshot, answer `wait_validare` |
| Builder, Reviewer | coding agents | build this repository on test data; fresh-context review of the diff |

- **Projects:** one per client; one Build project.
- **Issue kinds** (label + title prefix): `batch`, `job`, `recon`, `close`, `q:<kind>`. A `job`
  is a child of its month's `close`; `close` is blocked by `recon` while it has open questions.
- **Routines:** recheck the Reconcile window when a books export arrives; retry parked reads; the
  import agent's pull; the month's close on the cabinet's date.
- **Budgets:** per model role and per client, with hard stops: a stopped role refuses and a
  person is asked.
