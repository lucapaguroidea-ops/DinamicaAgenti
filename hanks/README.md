# Hanks — the model steps

One folder per hank: `hank.json` and `prompts/` (the role cards). A hank runs only where a model
reads or classifies; it ends by writing a JSON file that `kit verify` checks; it decides nothing
and never touches the dossier store (P7, P8). Written in WP-14, after R1 is confirmed and the
model ids are decided (D3).

| Hank | System | Codons | Output |
|---|---|---|---|
| `read-document` | Reader | read header and tables of a scan or statement PDF | `read.json` |
| `split-container` | Reader | propose an expense report's parts | `parts.json` |
| `judge-document` | One + Two | judge the document; explain the approval question | `verdict.json`, `explain.json` |
| `review-match` | One | confirm / contest / abstain on the kit's PRE verdict | `review.json` |
| `close-suggest` | One + Two | suggest the close action; explain; draft an explained rule | `suggest.json`, `explain.json`, `rule.json` |

Conventions:

- every codon `continuationMode: "fresh"`; files are the interface between codons;
- `model` is the exact id the catalog's role row pins, never an alias;
- a `budget` on every codon; runs started with `--max-cost` and `--max-time`;
- inputs mounted read-only; a rig copies them in and runs `kit prepare`;
- one client per run (P13).
