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

## File format

```yaml
catalog: Articol          # Axis | SourceDoc | JobKind | Articol | Mouth | ReconcileProfile |
                          # CloseKind | Control | Filing | QuestionKind | ModelRole
file_schema: 1
mode: base                # or additive (rows append to the base file of the same catalog)
rows:
  - id: ro_efactura_inbound
    status: draft         # draft | active (with approved: "owner, YYYY-MM-DD") | deprecated
    procedure: document   # the path: sorting | document | reconcile | close
    gate: {policy: first_n, first_n: 5}   # the gate: always | first_n | never_if_risk_low
    mouths: [intrare_factura_xml]         # a document path ends in a SAGA mouth
```

The row schemas are in `kit/catalog.py` (one closed model per catalog). Check the catalog with
`uv run kit catalog`. Rules the loader enforces:

- one base file per catalog; an additive file needs its base; ids unique across both;
- unknown catalog, top-level key, field, axis, axis value or referenced id is an error, so is a
  repeated YAML key or a `.yml` file; every problem is reported at once (P10);
- an articol with no `procedure` names no path, one with no `gate` is a silent post; only a
  document path names mouths, and it must name one (P2);
- scalars stay strings unless a field is an integer or a boolean: money (`"0.05"`), dates
  (`"2026-01-01"`) and accounts (`"401"`) are strings.
