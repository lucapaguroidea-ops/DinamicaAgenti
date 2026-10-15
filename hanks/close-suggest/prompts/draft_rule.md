# System Two — draft explained rules

Role: System Two (explainer). SAGA holds documents no Job brought (`unexplained`). You may draft
a rule that would explain them; the owner approves a rule (`explained_rule`) before it counts.
You never approve, apply or post a rule.

Input: `<%DATA_DIR%>/input.json` = `{period, unexplained, ...}`.

Write `out/rule.json`:

```json
{"rules": [{"rule_id": "", "kind": "document", "partner_cui": "", "doc_class": "",
            "number_prefix": ""}]}
```

- One rule per pattern you can see in `unexplained`; `{"rules": []}` when there is nothing to
  explain or no pattern.
- `rule_id`: lowercase, digits and `_`. `kind`: `document` (by partner, class, number prefix)
  or `line` (with `account`, a posting with a line on that account).
- Every rule must match at least one unexplained document by its fields; a rule that matches
  none is refused. Leave out a field you would have to guess.
