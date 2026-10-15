# Hanks — the model steps

One folder per hank: `hank.json` and `prompts/` (`system.md` and the role cards). A hank runs
only where a model reads or classifies; it ends by writing a JSON file that `kit verify` checks;
it decides nothing and never touches the dossier store (P7, P8). Runtime: `hankweave@0.12.0`
(`RESEARCH_LOG.md` R1); its schema is vendored in `schema/` and every `hank.json` is checked
against it in CI.

| Hank | System | Codons | Output |
|---|---|---|---|
| `read-document` | Reader | read header and tables of a scan or statement PDF | `read.json` |
| `split-container` | Reader | propose an expense report's parts | `parts.json` |
| `judge-document` | One + Two | judge the document; explain the approval question | `verdict.json`, `explain.json` |
| `review-match` | One | confirm / contest / abstain on the kit's PRE verdict | `review.json` |
| `close-suggest` | One + Two | suggest the close action; explain; draft an explained rule | `suggest.json`, `explain.json`, `rule.json` |

Conventions (checked by `kit hank check` and `tests/test_hanks.py`):

- the codons are exactly the hank's role rows (`catalog/50_control/model_roles.yaml`): codon id,
  `promptFile` = the role's card, `outputFiles` = only `out/{the role's output}`;
- `model` here is always `unpinned`, which the runtime itself refuses. `kit hank render` writes
  a run directory with each codon's model from its role row (by tier: `read-document` has an
  everyday and a strong role), and refuses the whole hank when a role has no pin (D3): the
  route's question then goes to a person;
- every codon `continuationMode: "fresh"`, no rig, `onFailure: "abort"`; files are the interface
  between codons (`explain` reads the `out/` file its System One codon wrote);
- a `budget` on every codon and on the hank; `kit hank render --data --out` prints the one
  command line the Dispatcher uses: the exact runtime version, `--headless`, `--max-cost`,
  `--max-time` from the hank's budget, never `-m`, `--force` or `--ignore-rig-failures`;
- the input is one data directory, mounted read-only (`<%DATA_DIR%>/input.json` and the
  document files), written for one client (P13) by `kit hank-run`, which then runs the hank and verifies it;
- `kit verify --role R --input input.json --output out/F.json` checks the file against the
  role's `answer` shape and its own check; with `--dossiers` a passing answer is stored under
  (role, input hash, card hash). The card hash covers the pin, `system.md` and the card, so a
  changed prompt or pin is never served an old answer.

The budgets are first values (dollars and seconds per codon), to be set per role in Paperclip
(WP-15).
