# Research log

External tools and formats, quoted or summarised from their sources with the date read (P16).
A fact marked **to confirm** may not be used to write a file until it is confirmed here.

## R1 · Hankweave (read 2026-10-07)

Sources: runtime README, <https://github.com/SouthBridgeAI/hankweave-runtime>; published example
`hank.json`, <https://github.com/SouthBridgeAI/multi-harness-hank> (raw file read in full). The
documentation site <https://hankweave.southbridge.ai> was not reachable from the session; its
pages on rigs, codons, configuration and budgets were seen as search summaries only.

Confirmed from the example `hank.json`:

```json
{
  "$schema": "https://unpkg.com/hankweave@latest/schemas/hank.schema.json",
  "meta": { "name": "…", "version": "1.1.0", "description": "…" },
  "globalSystemPromptFile": "./prompts/system.md",
  "overrides": { "budget": { "maxDollars": 2.00, "maxTimeSeconds": 600 } },
  "hank": [
    { "id": "architect", "name": "…", "model": "sonnet", "continuationMode": "fresh",
      "promptFile": "./prompts/01-architect.md", "checkpointedFiles": ["workspace/**/*"],
      "budget": { "maxDollars": 0.50 } },
    { "type": "loop", "id": "fresh-eyes", "name": "…",
      "terminateOn": { "type": "iterationLimit", "limit": 2 },
      "budget": { "maxDollars": 0.30 },
      "codons": [ { "id": "review", "model": "haiku", "continuationMode": "fresh",
                    "promptFile": "./prompts/05-fresh-eyes.md",
                    "checkpointedFiles": ["workspace/**/*"],
                    "outputFiles": [ { "copy": ["workspace/index.html"] } ] } ] }
  ]
}
```

- Model spellings seen: `sonnet`, `haiku`, `gpt-5.3-codex`, `pi/google/gemini-3-flash-preview`,
  `opencode/openai/gpt-5.4`. Harnesses: Claude Code, Codex, Gemini CLI, Pi, OpenCode; mixable in
  one hank.
- README: input data mounted read-only (`read_only_data_source/`, template variable
  `<%DATA_DIR%>`); git checkpoints at every codon boundary; a structured event journal;
  sentinels watch the event stream in parallel; budgets for cost, time and tokens.
- CLI: `bunx hankweave`; `bunx hankweave ./hank.json ./my-data`; `--max-cost`, `--max-time`, `-m`.

**Confirmed 2026-10-14** from the published package itself: npm `hankweave@0.12.0` (published
2026-09-18; tarball sha1 `2fcb142641cc80cf6dbe4f2dcdb8aa6c9e976668`, integrity
`sha512-L5zWmVZRZywhpgGsIX2Aje8r2NfSKrEevq5eBQns/o0B0yON3YCMPM4OL9+SaSonHGtQKOs/496oRrHCF+eNPw==`,
Apache-2.0). Its `schemas/hank.schema.json` is vendored unchanged in `hanks/schema/` (sha256
`bc7127748a350a9888ceeab5bdbcb6f9f308e3f22d2894ae21426fbca863fe91`); the CLI help was read from
the installed runtime. The documentation site is still unreachable from the session.

- **Closed schema.** The hank file, a codon, a loop, a budget, a rig operation and an output step
  all have `additionalProperties: false`. A codon requires `id`, `name`, `model`,
  `continuationMode` (`fresh` | `continue-previous`); `model` is a non-empty string.
- **`rigSetup`** (codon): operations `{type: "copy", copy: {from, to}}` (from: relative, inside
  the hank directory, no `..`, no symlinks) and `{type: "command", command: {run,
  workingDirectory: project | lastCopied}}`, each with `allowFailure` (default false): "Each
  operation must complete successfully for codon to start." A failing operation fails the codon
  unless `allowFailure` or the run flag `--ignore-rig-failures`.
- **`terminateOn`** (loop): only `{type: "iterationLimit", limit}` and `{type:
  "contextExceeded"}`. A loop cannot end on a condition a command computes: the kit's checks run
  after the run, never as a loop condition.
- **`outputFiles`**: `[{copy: [globs], beforeCopy?: [command]}]`, copied after the codon
  completes. **`onFailure`**: `abort` (default) | `retry` (with `retryConfig`) | `ignore`.
  **`budget`** (codon): `maxDollars`, `maxTimeSeconds`, `maxOutputTokens`, `maxContextTokens`,
  `onExceeded: complete | fail`; the hank's `overrides.budget` adds `allocation` and `shares`.
- **Resume:** `hankweave --execution <path>` "creates if doesn't exist, resumes if has state";
  `--start-new` never resumes; `--replay <path>` replays from recorded logs with no LLM calls.
- **Run flags:** `--headless`, `--max-cost`, `--max-time`, `--output <path>`, `--validate`
  (validate without running). Flags that defeat a gate here: `-m/--model` (overrides every
  codon's model), `--ignore-rig-failures`, `-f/--force` (overrides hash checks): the kit never
  passes them (`kit/hanks.py`, `NEVER_PASSED`).
- **`--validate` was run** on the five hanks: with the placeholder model `unpinned` the runtime
  refuses ("Model 'unpinned' not found in registry"); with an exact id in a scratch copy the
  hank file passes and only the provider self-test fails (no API key in the session); an
  unknown codon field fails as "Invalid hank file".
- Also seen, not used yet: `hankweave pack` makes a deterministic `.hank` bundle with a
  `hank.lock` (a hash per bundle); per-codon `sentinels`; `env`; `archiveOnSuccess`.

## R2 · Paperclip (read 2026-10-07)

Source: repository README, <https://github.com/paperclipai/paperclip>. The documentation site
<https://docs.paperclip.ing> was not reachable from the session.

- Node.js server and React UI; MIT. "If OpenClaw is an employee, Paperclip is the company."
- Organizations with goals; org charts with roles, titles, reporting lines; mixed human and
  agent org charts; budgets per agent.
- Adapters: Claude Code, OpenClaw, Codex, Cursor, Gemini CLI, OpenCode, Pi, Hermes, Grok Build,
  Kimi Code; "custom processes, HTTP endpoints, and external adapter packages extend the roster".
- Issues: company / project / goal / parent links; "atomic checkout with execution locks";
  first-class blocker dependencies; comments, documents, attachments; labels; inbox state; work
  products.
- Governance: board approval workflows; execution policies with review and approval stages;
  decision tracking; budget hard stops; agent pause / resume / terminate.
- Heartbeats: a DB-backed wake-up queue; triggers include assigned work, follow-up messages and
  schedules.
- Routines: cron, webhook and API triggers; each execution creates a tracked issue.
- Activity: mutating actions, heartbeat state changes, cost events, approvals, comments and work
  products are recorded as durable activity.
- Secrets by reference; local or S3-compatible file storage.
- CLI: `npx paperclipai@latest onboard`; `npx paperclipai configure`.

**Confirmed 2026-10-14** from the published packages (MIT): `paperclipai`,
`@paperclipai/server` and `@paperclipai/shared`, all `2026.1012.0` (published 2026-10-12); the
server's bundled agent skill (`skills/paperclip/references/api-reference.md`), its route code and
the shared zod validators; and a **live run** of that version (`paperclipai onboard --yes --run`,
`local_trusted`, loopback, embedded PostgreSQL, Node.js 24.11.1 in a scratch directory) driven by
`kit/paperclip.py` and `kit/dispatch.py`. The documentation site is still unreachable.

- **Adapters.** `process`: `command`, `args`, `cwd`, `env`, `timeoutSec`, `graceSec`; the run gets
  `PAPERCLIP_API_URL`, `PAPERCLIP_API_KEY` (a run-scoped JWT), `PAPERCLIP_RUN_ID`,
  `PAPERCLIP_AGENT_ID`, `PAPERCLIP_COMPANY_ID` and, on a wake, `PAPERCLIP_TASK_ID`,
  `PAPERCLIP_WAKE_REASON` (`issue_commented`, `issue_blockers_resolved`,
  `issue_children_completed`, `interaction_pending`, …); exit ≠ 0 is a failed run. `http`: `url`,
  `method`, `headers`, `payloadTemplate`, `timeoutSec`. A model is adapter config of the
  coding adapters only; the cabinet's agents are `process` / `http`.
- **Issues.** `POST /api/companies/{id}/issues` (`title`, `status`, `projectId`, `parentId`,
  `assigneeAgentId` | `assigneeUserId` (one assignee), `blockedByIssueIds`, `labelIds`,
  `idempotencyKey`); `PATCH /api/issues/{id}` (status, assignee, `comment`); statuses `backlog`,
  `todo`, `in_progress`, `in_review`, `done`, `blocked`, `cancelled`; 409 = another owns it (never
  retried), 422 = a refused transition. Labels: `POST /api/companies/{id}/labels` `{name ≤ 48,
  color #rrggbb}`. A person can be an issue's assignee (`assigneeUserId`) as well as an approver.
- **Questions (D2).** Issue-thread interactions, `POST /api/issues/{id}/interactions`:
  `ask_user_questions` (`payload.questionSet`, schema `paperclip.question_set.v1`, up to 64
  questions, `answerMode` `single_select` | `multi_select` | `text` with `textValidation`),
  `request_confirmation`, `request_checkbox_confirmation` (`defaultSelectedOptionIds` must meet
  `minSelected`; "defaults alone are not consent"), `request_item_verdicts`, `suggest_tasks`.
  `resolverPolicy` `anyone` | `not_creator` | `human_only` (snapshotted, never widened later);
  `addresseeAgentId` for an agent's question (only it or a board user resolves);
  `idempotencyKey` (≤ 255); `continuationPolicy` `wake_assignee`. `GET …/interactions` returns
  the list; a resolved card has `status` (`answered`, `accepted`, `rejected`, `expired`,
  `cancelled`, …), `result` (`answers[]` of `{questionId, optionIds, otherText}`, or `outcome` and
  `selectedOptionIds`) and `resolvedByUserId` / `resolvedByAgentId`. Answering:
  `…/{iid}/respond` `{answers}`, `…/accept` `{selectedOptionIds}`, `…/reject`.
- **Routines.** `POST /api/companies/{id}/routines` (`title`, `projectId`, `assigneeAgentId`,
  `concurrencyPolicy`, `catchUpPolicy`); `POST /api/routines/{id}/triggers` `schedule`
  (`cronExpression`, `timezone`) | `webhook` | `api`; the answer is `{trigger, secretMaterial,
  revision}`, and a webhook's `secretMaterial` (`webhookUrl`, `webhookSecret`) is shown once.
- **Budgets.** `POST /api/companies/{id}/budgets/policies` `{scopeType company | agent |
  project, scopeId, amount (cents), windowKind calendar_month_utc | lifetime, warnPercent,
  hardStopEnabled (default true)}`.
- **Seen live:** every set-up request of `paperclip/company.yaml` and a client was accepted (and
  checked against the zod validators with no field dropped); a second `apply` sent nothing; a
  refused judge led to a `human_only` `v3_approve` card with the issue `in_review`; a replayed
  wake added nothing; the board's `respond` came back as `answered` by `local-board` and was
  accepted by `kit answer`; `file` on a material month was refused and asked again on a new card
  that showed the error; a checkbox card was accepted with the ticked part only; the same
  idempotency key returned the same card. Found live and fixed: a trigger's id is nested
  (`trigger.id`); a create without an idempotency key that dies mid-request can repeat, so a
  request is now marked in flight first.
- In `local_trusted` mode a request with no bearer is the implicit board user `local-board`; a
  board key minted there did not resolve to a user and was read as an agent token (401). The
  kit's client always sends a key: run Paperclip `authenticated` (D4).

## R3 · RO e-Factura: UBL 2.1, EN 16931 and CIUS-RO (read 2026-10-07)

The official CIUS-RO pages (mfinante.gov.ro, anaf.ro) and the OASIS UBL 2.1 page
(docs.oasis-open.org) were **not reachable** from the session. What the reader relies on comes
from the official EN 16931 validation artefacts, which CIUS-RO extends.

**Source.** CEN/TC 434 validation artefacts for EN 16931, published by the European Commission:
<https://github.com/ConnectingEurope/eInvoicing-EN16931>, release `validation-1.3.16`
(2026-04-10, commit `b6c9e06`), EUPL 1.2. Files read in full: `ubl/schematron/EN16931-UBL-validation.sch`,
`ubl/schematron/UBL/EN16931-UBL-model.sch`, `ubl/schematron/abstract/EN16931-model.sch`. The README
says: "This repository does not contain eInvoicing-EN16931 rules for any CIUS."

Namespaces (`EN16931-UBL-validation.sch`):

```
ubl  urn:oasis:names:specification:ubl:schema:xsd:Invoice-2
cn   urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2
cac  urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2
cbc  urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2
```

Bindings used by the reader (`EN16931-UBL-model.sch`), quoted:

| Business term | UBL binding |
|---|---|
| Invoice (root) | `/ubl:Invoice \| /cn:CreditNote` |
| BR-01 specification identifier | `cbc:CustomizationID` |
| BR-02 invoice number (BT-1) | `cbc:ID` |
| BR-03 issue date (BT-2) | `cbc:IssueDate` |
| BR-04 type code (BT-3) | `cbc:InvoiceTypeCode` or `cbc:CreditNoteTypeCode` |
| BR-05 currency (BT-5) | `cbc:DocumentCurrencyCode` |
| BR-06 seller name | `cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName` |
| BR-07 buyer name | `cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName` |
| VAT identifiers (BT-31, BT-48) | `cac:PartyTaxScheme[cac:TaxScheme/cbc:ID='VAT']/cbc:CompanyID` |
| Legal registration identifier (BT-30) | `cac:Party/cac:PartyLegalEntity/cbc:CompanyID` |
| Document totals | `cac:LegalMonetaryTotal`: `cbc:LineExtensionAmount` (BT-106), `cbc:TaxExclusiveAmount` (BT-109), `cbc:TaxInclusiveAmount` (BT-112), `cbc:PayableAmount` (BT-115), optional `cbc:AllowanceTotalAmount`, `cbc:ChargeTotalAmount`, `cbc:PrepaidAmount`, `cbc:PayableRoundingAmount` |
| Total VAT (BT-110) | `cac:TaxTotal/cbc:TaxAmount[@currencyID = DocumentCurrencyCode]` |
| VAT breakdown | `cac:TaxTotal/cac:TaxSubtotal` |
| Invoice line (BG-25) | `cac:InvoiceLine \| cac:CreditNoteLine`: `cbc:ID` (BR-21), `cbc:LineExtensionAmount` (BR-24), `cac:Item/cbc:Name` (BR-25), `cac:Price/cbc:PriceAmount` (BR-26), `cac:Item/cac:ClassifiedTaxCategory` (`cbc:ID`, `cbc:Percent`) |

Rules the reader enforces, quoted from `EN16931-model.sch` (all `flag="fatal"`):

- **BR-CO-10** "Sum of Invoice line net amount (BT-106) = Σ Invoice line net amount (BT-131)."
- **BR-CO-13** "Invoice total amount without VAT (BT-109) = Σ Invoice line net amount (BT-131) -
  Sum of allowances on document level (BT-107) + Sum of charges on document level (BT-108)."
- **BR-CO-15** "Invoice total amount with VAT (BT-112) = Invoice total amount without VAT (BT-109)
  + Invoice total VAT amount (BT-110)."
- **BR-CO-16** "Amount due for payment (BT-115) = Invoice total amount with VAT (BT-112) -Paid
  amount (BT-113) +Rounding amount (BT-114)."
- **BR-CO-09** VAT identifiers carry an ISO 3166-1 alpha-2 prefix (e.g. `RO`).
- **BR-CO-26** "the Seller identifier (BT-29), the Seller legal registration identifier (BT-30)
  and/or the Seller VAT identifier (BT-31) shall be present."
- **BR-DEC-*** amounts have at most two decimals.

**Secondary sources (not official; to confirm on the official page before relying on them):**

- CustomizationID for CIUS-RO 1.0.1:
  `urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1`
  (search summaries of utcluj.ro, dev.to, validatefin.com, 2026-10-07). The reader records the
  value; it does not require it.
- CIUS-RO is approved by MF Order 1366/2021 and adds the BR-RO rules (search summaries).
- The SPV download is a zip holding the invoice `{id}.xml` and its signature (named
  `semnatura_{id}.xml` in common use), per the Ministry of Finance's API presentation
  (`mfinante.gov.ro/static/10/eFactura/prezentare apeluri API E-factura.pdf`, blocked) as relayed
  by search summaries. The reader therefore tells the invoice from its signature by the XML root
  element, never by the file name.
- A Romanian credit note may arrive as a UBL `CreditNote` or as an `Invoice` with negative
  amounts; the reader marks both as storno. **To confirm** on a test-firm import.
- A seller without a VAT number is identified by its CUI in `PartyLegalEntity/cbc:CompanyID`
  (BT-30); the reader takes the VAT identifier first, then BT-30. **To confirm** against BR-RO.

## R4 · SAGA C: "Import date", user configuration, report exports — to read before WP-10
