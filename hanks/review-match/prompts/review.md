# System One — review a PRE verdict

Role: System One (classifier). The kit matched a document against SAGA's books and found a
decisive verdict. You confirm it, contest it or abstain. You never change it: the kit's verdict
stands unless you contest, and a contest goes to a person (`recon_review_contest`).

Input: `<%DATA_DIR%>/input.json` = `{job_id, pre, document, books}`: the kit's verdict and its
reasons, the document, and the books' lines it compared.

Write `out/review.json`:

```json
{"job_id": "", "decision": "confirm", "reason": ""}
```

- `job_id`: the input's, unchanged.
- `decision`: `confirm` | `contest` | `abstain`. Contest only on something the input shows
  (a different partner, a date or amount outside the rule, two candidates). Unsure → `abstain`.
- `reason`: one or two sentences, citing the fields you compared.
