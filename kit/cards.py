"""Question cards: a question kind as a Paperclip issue-thread interaction, and back (D2).

The owner decided (2026-10-14, D2) that a question carries its answer in Paperclip's own cards
(``POST /api/issues/{id}/interactions``, ``RESEARCH_LOG.md`` R2). ``card`` turns a question kind
and the question asked into the request body; ``answer_from_result`` turns the stored result
back into the kind's answer, which then goes through ``kit answer`` like any other (P10, P12):
the card is a form, never the gate.

- Each answer field is one question of an ``ask_user_questions`` card (``paperclip.question_set.
  v1``): an enum or a bool is a single choice; a field the question offers choices for is a
  choice; an atom (slug, cui, period, sha256, int, str) is a text field with its pattern; a
  list or an object is JSON text. Optional fields are not required.
- ``decont_split`` with a Reader proposal is a ``request_checkbox_confirmation`` over the proposed
  parts: the person ticks the parts that are right; none is preselected. Without a proposal it
  is a JSON text field.
- A person's question is ``human_only`` (an agent never answers it, P5); the SAGA agent's is
  addressed to that agent. The idempotency key is the issue, the kind, the question's hash and
  the attempt: asking the same question twice is one card; a refused answer is asked again on a
  new card that carries the error.
"""

from __future__ import annotations

import json
from typing import Any

from kit.catalog import Catalog
from kit.questions import T, parse_type, question_hash

QUESTION_SET = "paperclip.question_set.v1"
YES, NO = "true", "false"

_PATTERNS = {
    "slug": r"^[a-z][a-z0-9_]*$",
    "cui": r"^(RO)?[0-9]{2,10}$",
    "period": r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    "sha256": r"^[0-9a-f]{64}$",
}

# What the accountant reads on each field (Romanian, plain). Every field of every kind has one.
PROMPTS: dict[tuple[str, str], str] = {
    ("define_class", "source_doc_id"): "Ce fel de document este?",
    ("bon_cui_unclear", "cu_cui"): "Bonul are CUI-ul clientului?",
    ("bon_cui_unclear", "fara_cui"): "Bonul este fără CUI-ul clientului?",
    ("decont_split", "parts"): "Părțile decontului (JSON: part_hash, source_doc_id, kinds)",
    ("define_articol", "articol_id"): "Pe ce articol de cale merge documentul?",
    ("v3_approve", "decision"): "Aprobați documentul?",
    ("v3_approve", "edit"): "Corectura (JSON), doar pentru «edit»",
    ("wait_validare", "validated"): "Documentul este validat în SAGA?",
    ("wait_validare", "saga_doc_key"): "Cheia documentului în SAGA",
    ("need_rj_export", "export_id"): "Exportul registrului jurnal încărcat (id)",
    ("recon_ambiguous", "action"): "Documentul este deja în SAGA?",
    ("recon_ambiguous", "sink_line_ids"): "Liniile din SAGA care îl conțin",
    ("recon_review_contest", "action"): "Verificarea contestă verdictul. Ce este adevărat?",
    ("recon_how_mismatch", "ack_mismatch"): "Acceptați înregistrarea din SAGA așa cum e?",
    ("recon_how_mismatch", "open_storno"): "Deschideți o stornare?",
    ("v2_close", "action"): "Ce faceți cu luna?",
    ("v2_close", "explained_rule"): "Regula explicată (id), dacă e cazul",
    ("v4_codit", "accept"): "Acceptați CO.DiT pentru luna următoare?",
    ("v4_codit", "skip"): "Săriți peste CO.DiT luna aceasta?",
    ("v4_codit", "edit"): "Modificări CO.DiT (JSON), dacă acceptați",
    ("v4_codit", "seed_next"): "Valori pentru luna următoare (JSON)",
    ("explained_rule", "rule_id"): "Regula explicată (id)",
    ("control_disposition", "control_id"): "Controlul (id)",
    ("control_disposition", "disposition"): "Ce faceți cu controlul eșuat?",
    ("control_disposition", "rule_id"): "Regula explicată (id), pentru «explained_rule»",
    ("filing_receipt", "filing_id"): "Declarația (id)",
    ("filing_receipt", "period"): "Perioada (AAAA-LL)",
    ("filing_receipt", "receipt_key"): "Recipisa încărcată (cheie)",
    ("filing_receipt", "submitted_by"): "Cine a depus declarația",
}


class CardError(ValueError):
    """A card cannot be made, or its result is not an answer (skipped, withdrawn, malformed)."""


def _label(value: str) -> str:
    return {YES: "da", NO: "nu"}.get(value, value.replace("_", " "))


def _question(kind: str, field: str, t: T, choices: list[str] | None) -> dict:
    q: dict[str, Any] = {
        "id": field,
        "prompt": PROMPTS.get((kind, field), field),
        "required": not t.optional,
    }
    if t.kind == "enum" or choices:
        values = list(choices or t.values)
        q["answerMode"] = "multi_select" if t.kind == "list" else "single_select"
        q["options"] = [{"id": str(v), "label": _label(str(v))} for v in values]
    elif t.kind == "bool":
        q["answerMode"] = "single_select"
        q["options"] = [{"id": YES, "label": "da"}, {"id": NO, "label": "nu"}]
    elif t.kind in _PATTERNS:
        q["answerMode"] = "text"
        q["textValidation"] = {"pattern": _PATTERNS[t.kind], "maxLength": 200}
    elif t.kind == "int":
        q["answerMode"] = "text"
        q["textValidation"] = {"inputType": "integer"}
    elif t.kind == "str":
        q["answerMode"] = "text"
        q["textValidation"] = {"minLength": 1, "maxLength": 4000}
    else:  # a list, a record or an object: JSON
        q["answerMode"] = "text"
        q["helpText"] = "JSON"
        q["textValidation"] = {"minLength": 1, "maxLength": 100000}
    return q


def _proposed_parts(question: dict) -> list[dict]:
    return list((question.get("proposed") or {}).get("parts") or [])


def card(
    cat: Catalog,
    kind: str,
    issue: str,
    question: dict,
    attempt: int = 0,
    error: str | None = None,
    saga_agent_id: str | None = None,
) -> dict:
    """The body of ``POST /api/issues/{id}/interactions`` asking ``question`` of its actor.
    ``question["choices"]`` may offer the values of a field (``{field: [values]}``)."""
    row = cat.get("QuestionKind", kind)  # an unknown kind is an error (P10)
    qhash = question_hash(question)
    body: dict[str, Any] = {
        "idempotencyKey": f"q:{issue}:{kind}:{qhash[:16]}:{attempt}",
        "title": f"{kind} · {issue}"[:240],
        "continuationPolicy": "wake_assignee",
    }
    if row.actor == "accountant":
        body["resolverPolicy"] = "human_only"
    else:
        if not saga_agent_id:
            raise CardError(f"{kind} is the SAGA agent's: its agent id is needed")
        body["addresseeAgentId"] = saga_agent_id
    shown = {k: v for k, v in question.items() if k not in ("choices", "error")}
    details = "```json\n" + json.dumps(shown, indent=2, ensure_ascii=False) + "\n```"
    if error:
        details = f"**Răspunsul anterior a fost refuzat:** {error}\n\n" + details

    parts = _proposed_parts(question)
    if kind == "decont_split" and parts:
        body["kind"] = "request_checkbox_confirmation"
        body["payload"] = {
            "version": 1,
            "prompt": "Bifați părțile corecte ale decontului.",
            "detailsMarkdown": details,
            "options": [
                {
                    "id": p["part_hash"][:120],
                    "label": (p.get("name") or p["part_hash"][:12])[:120],
                    "description": f"{p['source_doc_id']} · {', '.join(p['kinds'])}"[:500],
                }
                for p in parts
            ],
            # nothing preselected: the person ticks each part (the proposal is a model's);
            # an empty choice is refused by kit answer and asked again
            "acceptLabel": "Confirm părțile",
            "rejectLabel": "Nu sunt corecte",
            "rejectRequiresReason": True,
        }
        return body

    choices = question.get("choices") or {}
    body["kind"] = "ask_user_questions"
    body["payload"] = {
        "version": 1,
        "questionSet": {
            "schema": QUESTION_SET,
            "title": f"{kind}"[:1000],
            "description": details,
            "questions": [
                _question(kind, field, parse_type(expr), choices.get(field))
                for field, expr in row.answer.items()
            ],
        },
    }
    return body


def answer_from_result(cat: Catalog, kind: str, question: dict, interaction: dict) -> dict:
    """The kind's answer from a resolved interaction (``GET /api/issues/{id}/interactions``).
    The answer is checked afterwards by ``kit answer``; here only its form is read."""
    row = cat.get("QuestionKind", kind)
    result = interaction.get("result") or {}
    status = interaction.get("status")
    if status not in ("answered", "accepted", "rejected"):
        raise CardError(f"not answered: the card is {status}")
    if interaction.get("kind") == "request_checkbox_confirmation":
        if result.get("outcome") != "accepted":
            reason = result.get("reason") or ""
            raise CardError(f"not answered: {result.get('outcome')} {reason}".strip())
        chosen = set(result.get("selectedOptionIds") or [])
        parts = [
            {k: v for k, v in p.items() if k != "name"}
            for p in _proposed_parts(question)
            if p["part_hash"][:120] in chosen
        ]
        return {"parts": parts}

    if result.get("outcome") or result.get("cancelled") or result.get("expirationReason"):
        why = result.get("outcome") or result.get("expirationReason") or "cancelled"
        raise CardError(f"not answered: {why}")
    given = {a["questionId"]: a for a in result.get("answers") or []}
    unknown = set(given) - set(row.answer)
    if unknown:
        raise CardError(f"answers to questions the card did not ask: {sorted(unknown)}")
    answer: dict[str, Any] = {}
    for field, expr in row.answer.items():
        t = parse_type(expr)
        a = given.get(field)
        if a is None:
            continue
        ids = [i for i in a.get("optionIds") or [] if i]
        text = (a.get("otherText") or "").strip()
        try:
            answer[field] = _value(t, ids, text, field in (question.get("choices") or {}))
        except (ValueError, json.JSONDecodeError) as exc:
            raise CardError(f"{field}: {exc}") from exc
        if answer[field] is None:
            del answer[field]
    return answer


def _value(t: T, ids: list[str], text: str, offered: bool) -> Any:
    if t.kind == "bool":
        return None if not ids else ids[0] == YES
    if t.kind == "enum" or (offered and t.kind != "list"):
        return ids[0] if ids else None
    if t.kind == "list" and offered:
        return [int(i) if t.item and t.item.kind == "int" else i for i in ids]
    if not text:
        return None
    if t.kind == "int":
        return int(text)
    if t.kind in ("list", "record", "object"):
        return json.loads(text)
    return text
