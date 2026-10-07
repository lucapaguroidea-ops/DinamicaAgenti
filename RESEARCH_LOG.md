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

## R3 · RO e-Factura UBL (CIUS-RO) — to read before WP-07

## R4 · SAGA C: "Import date", user configuration, report exports — to read before WP-10
