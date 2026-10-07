# Catalog — the ontology

Every articol de cale, source document, SAGA mouth, question kind, control and model role is a
YAML row here (P2). The gate kit loads it; the procedures walk it. Rows are written in WP-05.

- Every row enters as `status: draft`; it becomes `active` only once proven in a SAGA C test firm
  and approved by the owner (P14).
- A duplicate id is an error; an unknown articol, kind or role is an error, not a skip (P10).
- Files in `60_practice/` may be `mode: additive`: their rows append to a base file of the same
  catalog name.

| Section | Holds |
|---|---|
| `10_law_firm/` | CO.DiT axes and pairs (legal form × tax × VAT × exigibility), rates by year |
| `20_document/` | source documents (what a file is, when it may emit) and Job kinds |
| `30_path/` | articole de cale (filters, require / forbid, approval policy, expected accounts, mouths), SAGA mouths, procedure definitions |
| `40_sink/` | reconcile profiles (PRE / POST) and close kinds |
| `50_control/` | question kinds (actor, answer schema, check) and model roles (system, pinned model, role card) |
| `60_practice/` | month controls, filings, statement grain, additive rows |
