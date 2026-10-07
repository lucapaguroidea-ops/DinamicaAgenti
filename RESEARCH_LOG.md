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

**To confirm** on the documentation site before WP-14:

- `rigSetup` on a codon, with `copy` (`{ "type": "copy", "copy": { "from", "to" } }`) and command
  operations; whether a failing command stops the codon.
- `terminateOn` types beyond `iterationLimit` and `contextExceeded`; whether a loop can end on a
  condition a command computes.
- How a run is resumed from a checkpoint (CLI).

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

**To confirm** on the documentation site before WP-15: the Process and HTTP adapter
configuration; the API for creating, blocking and closing issues; whether a person can be an
issue's assignee as well as an approver; how a structured answer is attached (D2).

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
