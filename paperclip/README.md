# Paperclip — the company set-up

The firm around the system (`ARCHITECTURE.md` §8), on `paperclipai@2026.1012.0`
(`RESEARCH_LOG.md` R2). `company.yaml` is the company; nothing here is configured by hand.

- **Company:** the cabinet; goal: every client month closed in SAGA C through its gates. Board =
  the owner.
- **Agents:** Dispatcher (`process` adapter, `uv run kit dispatch`, no model); Reader and
  Classifier (`process`, `kit hank-run`, which is planned: until D3 every hank refuses anyway); SAGA
  import agent (`http` adapter, created paused: a person until the program is built, and a board
  user answers its cards). No model is configured on an agent: a model is pinned per role in
  the catalog (P8), and `kit paperclip setup` refuses a `model` here.
- **Labels:** `batch`, `job`, `recon`, `close`, `hank`, `question`, `hold`. An issue's title is
  `{key} [{cui}]`, e.g. `job:j_… [41526372]`, `close:41526372:2026-09 [41526372]`.
- **Questions (D2):** a card on the work issue (`kit/cards.py`), `human_only` for a person; the
  issue waits `in_review` until it is answered; the answer goes through `kit answer`.
- **Projects and routines:** one Build project; per client a project with its hard-stop budget
  and four routines (recheck the Reconcile window when a books export arrives — a webhook;
  retry parked reads; the import agent's pull; the month's close on the cabinet's date).
- **Budgets:** hard stops per agent, per client project and for the company. The values marked
  `owner` start at 0, which spends nothing.

```bash
export KIT_HOME=… DOSSIERS=… SAGA_AGENT_URL=… ACCOUNTANT_USER_ID=…   # D4
uv run kit paperclip setup                                  # print the requests
PAPERCLIP_API_URL=… PAPERCLIP_API_KEY=… \
  uv run kit paperclip setup --apply --state paperclip-state.json
uv run kit paperclip setup --client 41526372 --client-cents 2000 --apply --state paperclip-state.json
```

The state file keeps the ids (keep it with the dossiers, outside this repository); a webhook's
signing secret is written once to `paperclip-state.secrets.json` (mode 0600). The Dispatcher
reads the state from `POARTA_PAPERCLIP_STATE` and the dossiers from `POARTA_DOSSIERS`.
