# Law

Status: **in force, approved by the owner on 2026-10-07**, from the design note (`docs/design/`).
A change to any principle is the owner's dated decision.

**How to read it.** Every principle has a permanent id (`P1` …), never reused; a removed
principle's id is retired. `[test]` marks a principle the build must enforce: a failing test
fails the build, and the citation test (BUILD WP-03) checks that every `[test]` principle has a
test naming it. `[owner, date]` marks a principle that came from a dated owner decision.

## 1. The unit

- **P1 · The unit is an articol de cale.** A bookkeeping state that already knows its next path
  (*cale*) and the gate (*poartă*) that must open before the document moves. A change that cannot
  be stated as "which articol, and is its poartă open?" is not ready.
- **P2 · The catalog is the ontology.** Every articol, source document, SAGA mouth, question
  kind, control and model role is a YAML row in `catalog/`. The procedures walk it. An articol
  that names no path is a comment; a path with no gate is a silent post. [test]

## 2. SAGA

- **P3 · One mouth, one eye.** SAGA C is the only place anything is posted, by XML → Import
  date → Validare. SAGA's report exports (registru jurnal, balanță, purchase and sales journals)
  are the only eye. Nothing writes SAGA's database. [test]
- **P4 · Not a ledger.** No store holds a chart of accounts, a journal or a trial balance as
  books. The system holds an expected set and snapshots of what SAGA shows. [test]
- **P5 · Validare is a person's.** An import agent may import. Validare, Devalidare, closing a
  month and restoring a backup stay with a person. A month closed in SAGA gets nothing. [test]

## 3. Documents

- **P6 · XML first.** Where a document exists as XML, the XML is the document and the only
  extract source; its PDF is a companion and is not read. A Romanian PDF invoice without its UBL
  is not primary. [test]

## 4. Routes and models

- **P7 · Routes read facts.** Which step comes next is decided by the gate kit from stored
  facts. No model on a route, ever. [test]
- **P8 · Models by role, pinned.** A model acts only inside a model step (a Hankweave codon), in
  a role the catalog names, with one exact model pinned. Its output is checked by the gate kit
  before it becomes a fact. An unset model means the role refuses and a person is asked. [test]
- **P9 · Ask before acting.** Every question to a person comes before any side effect of that
  step. A repeated run reaches the same state: side effects are keyed so that a second attempt
  is a no-op. [test]
- **P10 · Fail closed.** Unknown fields in an answer or a record are refused. Money and fiscal
  dates are strings outside the code that computes on them. An unknown articol, kind or question
  is an error, not a skip. [test]

## 5. The month

- **P11 · Material is never filed.** A month whose differences are material cannot be marked
  file; a model cannot clear material. [test]
- **P12 · Every answer is recorded.** Who answered, when, what was proposed, what was chosen and
  the outcome, append-only; the same for every control's disposition.

## 6. Clients

- **P13 · Clients never mix.** No client's data in another client's run, prompt, export or
  workspace. Every record and model call carries the client's CUI and is refused on a mismatch.
  [test]

## 7. Changing the system

- **P14 · Proven before active.** A catalog row is `draft` until it has gone round-trip through
  a SAGA C test firm and the owner approves it. Synthetic proof alone keeps it `draft`.
- **P15 · Gates change only on evidence.** A question, control or gate is added, removed or
  relaxed only by the owner, with the evidence of the friction it costs and the control it gives.
- **P16 · External formats from official sources.** No SAGA tag, export layout or tool
  configuration is guessed: it is quoted from its official source with the date in
  `RESEARCH_LOG.md`, or proven by a test-firm import.

## 8. Lexicon

| Term | Means | Does not mean |
|---|---|---|
| Articol de cale | state + path + gate; a catalog row | a comment |
| Cale | a pre-defined walk: document primar × Romanian accounting × tax | a model's trajectory |
| Poartă | a guard on a hop | a chat "ok" |
| Document primar | factură, UBL, bon, extras | notă contabilă |
| Job | the posting unit, one per source document | a month's close |
| Close run | one client-month | a Job |
| Mouth | a SAGA import module (XML or DBF) | a database write |
| Eye | SAGA's report exports read back | a model reading a screen |
| Expected set | the totals the month's documents imply | a general ledger |
| Hank | a Hankweave program of codons | a decision maker |
| Gate kit | the deterministic core in `kit/` | a model |
| Dossier | one client's facts, written only by the gate kit | Paperclip's database |

Romanian domain words stay Romanian; code identifiers stay English.
