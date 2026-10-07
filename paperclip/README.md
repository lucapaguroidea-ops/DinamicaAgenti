# Paperclip — the company set-up

The firm around the system (`ARCHITECTURE.md` §8). Written in WP-15, after R2 is confirmed and
D2 is decided.

- **Company:** the cabinet; goal: every client month closed in SAGA C through its gates. Board =
  the owner.
- **Roles:** Accountant(s) (people); Dispatcher (Process adapter, no model, runs `kit route`);
  Reader, Classifier, Explainer (run the hanks); SAGA import agent (HTTP adapter); Builder and
  Reviewer (coding agents, test data only).
- **Projects:** one per client; one Build project.
- **Labels:** `batch`, `job`, `recon`, `close`, `q:<kind>`.
- **Links:** a `job` is a child of its month's `close`; `close` is blocked by `recon` while it
  has open questions; a question blocks its work issue.
- **Routines:** recheck the Reconcile window when a books export arrives; retry parked reads; the
  import agent's pull; the month's close.
- **Budgets:** per model role and per client, with hard stops.
