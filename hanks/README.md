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
- every stored answer says who gave it (P8, P12): `kit hank-run` stores its run's answers as
  the role's pinned model's, with the run directory; `kit verify --dossiers` needs
  `--operator` and stores the file as that operator's, never as a model's. A key holds one
  answer: the same answer from the same source again is a no-op, any other is refused.
- a cache hit is all or nothing: every role of the hank has a stored answer, all from one
  model run. On a partial hit the run answers every role (an explanation reads its own run's
  verdict); a run's answers are stored only when every role's passed, and only for the roles
  with no stored answer.
- an operator's answer never stands in for a model run on a real client's dossier: when a
  cached answer is an operator's (or has no recorded source), `kit hank-run` runs nothing,
  writes no fact from it and refuses the hank the way an unpinned role does (P8): the hank's
  refusal facts go to the work issue with the reason (`_hank_held`), and its route goes on
  the cautious way (a read to the strong tier, a doubtful verdict to a person's card, a
  review contested, no close suggestion). Only on a dossier marked a test firm
  (`kit dossier mark-test-firm`) is it used, for rigs and development loops with no live
  model, and the work issue's facts say whose answer it was (`_answer_sources`).

The budgets are first values (dollars and seconds per codon), to be set per role in Paperclip
(WP-15).
