"""The Dispatcher: one wake of a Paperclip issue, routed by the kit (ARCHITECTURE §8, P7).

On every wake the Dispatcher reads the issue's facts from the client's dossier (``issue_facts``:
what kit steps wrote, what ``kit verify`` passed, what people answered, what refused), first
takes in an answered card, then asks ``kit route`` for the next step and does it:

- **kit**: the step's executor (``kit/steps.py``) reads the dossier and writes its facts; a step
  that cannot run is held for a person with the reason (a step never pretends to have run);
- **hank**: the hank is rendered with the catalog's pins; while a role is unpinned (D3) it
  refuses, and the refusal is written as the fail-closed fact (a doubtful verdict, a contest, a
  read not confirmed, a suggestion not made), so the route's question goes to a person;
- **ask**: the question kind's card on the issue (``kit.cards``, D2), the issue ``in_review``;
  an answer comes back on the next wake and goes through ``kit answer`` (P10, P12); refused, it
  is asked again on a new card with the error; an accepted answer whose effect has no executor
  yet is held, never asked twice;
- **wait** / **hold** / **done**: the issue's status, its assignee and one comment.

Every write to the dossier is keyed (``add_facts``), so a replayed wake adds nothing (P9). Only
a person answers a person's card (``human_only``); the Dispatcher never answers one (P5).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kit.cards import CardError, answer_from_result, card
from kit.catalog import Catalog
from kit.hanks import DOUBTFUL, HankHeld, HankRefused, render
from kit.paperclip import Client
from kit.questions import answer_question, question_hash
from kit.route import _ROUTES, Step
from kit.steps import APPLY, CONTEXT, EXECUTORS, LIVE_CONTEXT, Executor, StepError, derive
from kit.store import Dossier, StoreError

MAX_STEPS = 12
DONE_CANCELLED = ("rejected", "failed", "not_emitted", "refused")


@dataclass
class Company:
    """The Paperclip ids the Dispatcher needs (the setup's state file)."""

    ids: dict[str, str]
    accountant_user_id: str

    def id(self, ref: str) -> str:
        if ref not in self.ids:
            raise KeyError(f"no Paperclip id for {ref!r}: run kit paperclip setup first")
        return self.ids[ref]


@dataclass
class Tick:
    issue: str
    steps: list[str] = field(default_factory=list)
    ended: str = ""


# What a refused hank leaves behind: the cautious reading of no answer (P8).
REFUSALS: dict[str, Callable[[dict], dict]] = {
    "read-document": lambda f: {"read_runs": f.get("read_runs", 0) + 1, "read_confirmed": False},
    "judge-document": lambda f: {"judged": True, "verdict": dict(DOUBTFUL)},
    "review-match": lambda f: {
        "to_review": [],
        "contested": list(f.get("contested", [])) + list(f.get("to_review", [])),
    },
    "close-suggest": lambda f: {"suggested": True},
}


# ----- the wake -----


def _digest(facts: dict) -> str:
    """The facts a step ran on: the same step on the same facts is one write (P9)."""
    return question_hash(facts)[:16]


def _route_facts(procedure: str, facts: dict) -> dict:
    model = _ROUTES[procedure][0]
    return {k: v for k, v in facts.items() if k in model.model_fields}


def _title(issue: str, cui: str) -> str:
    return f"{issue} [{cui}]"


def ensure_issue(
    d: Dossier,
    pc: Client,
    co: Company,
    issue: str,
    parent: str | None = None,
    assignee: str = "agent:dispatcher",
) -> str:
    """The Paperclip issue of one of ours, created once (idempotency key = our key)."""
    pid = d.paperclip_id(issue)
    if pid:
        return pid
    procedure = issue.split(":", 1)[0]
    body: dict[str, Any] = {
        "title": _title(issue, d.client_cui),
        "status": "todo",
        "projectId": co.id(f"project:{d.client_cui}"),
        "assigneeAgentId": co.id(assignee),
        "labelIds": [co.id(f"label:{procedure}")],
        "idempotencyKey": f"{d.client_cui}:{issue}",
    }
    if parent:
        body["parentId"] = ensure_issue(d, pc, co, parent)
    out = pc.request("POST", f"/api/companies/{co.id('company')}/issues", body)
    return d.link_issue(issue, out["id"])


def _write(
    d: Dossier, pc: Client, co: Company, issue: str, key: str, source: str, fields: dict
) -> None:
    """Store a step's facts; open the issues it names (``_spawn``) and hand the ones it moved
    back to the Dispatcher (``_wake``): an assignment wakes the assignee (R2)."""
    spawn, wake = fields.pop("_spawn", []), fields.pop("_wake", [])
    d.add_facts(issue, key, source, fields)
    for child, parent in spawn:
        ensure_issue(d, pc, co, child, parent)
        wake.append(child)
    for other in dict.fromkeys(wake):
        if other != issue:
            _patch(
                pc,
                ensure_issue(d, pc, co, other),
                status="todo",
                assigneeAgentId=co.id("agent:dispatcher"),
                assigneeUserId=None,
            )


def _patch(pc: Client, pid: str, **body) -> None:
    pc.request("PATCH", f"/api/issues/{pid}", body)


def dispatch(
    cat: Catalog,
    repo: Path,
    d: Dossier,
    issue: str,
    pc: Client,
    co: Company,
    executors: dict[tuple[str, str], Executor] | None = None,
) -> Tick:
    executors = EXECUTORS if executors is None else executors
    procedure = issue.split(":", 1)[0]
    if procedure not in _ROUTES:
        raise ValueError(f"{issue}: not an issue of a procedure ({sorted(_ROUTES)})")
    pid = ensure_issue(d, pc, co, issue)
    tick = Tick(issue)

    for _ in range(MAX_STEPS):
        facts = d.facts(issue)
        pending = facts.get("_card")
        if pending:
            if not _take_answer(cat, d, issue, pid, pc, co, pending, tick):
                return tick
            continue
        step: Step = _ROUTES[procedure][1](
            _ROUTES[procedure][0].model_validate(_route_facts(procedure, derive(d, issue, facts)))
        )
        tick.steps.append(f"{step.kind}:{step.name}")

        if step.kind == "kit":
            fn = executors.get((procedure, step.name))
            if fn is None:
                return _hold(
                    pc, pid, co, tick, f"kit step {step.name} is not wired to the Dispatcher yet"
                )
            try:
                fields = fn(cat, d, issue, facts, step.detail)
            except KeyError as exc:
                why = f"kit step {step.name}: the fact {exc} is not established yet"
                return _hold(pc, pid, co, tick, why)
            except (StepError, StoreError, ValueError) as exc:
                return _hold(pc, pid, co, tick, f"kit step {step.name}: {exc}")
            _write(d, pc, co, issue, f"kit:{step.name}:{_digest(facts)}", "kit", fields)
        elif step.kind == "hank":
            refused = _hank(cat, repo, step, facts)
            if refused is None:
                return _hand_off(cat, d, pc, co, issue, pid, step, facts, tick)
            d.add_facts(
                issue, f"refusal:{step.name}:{facts.get('read_runs', 0)}", "refusal", refused
            )
            pc.request(
                "POST",
                f"/api/issues/{pid}/comments",
                {"body": f"{step.name}: no pinned model (D3): a person is asked instead."},
            )
        elif step.kind == "ask":
            return _ask(cat, d, issue, pid, pc, co, step, facts, tick)
        elif step.kind == "wait":
            _patch(pc, pid, status="in_review", comment=f"Waiting: {step.reason or step.name}.")
            tick.ended = f"wait:{step.name}"
            return tick
        elif step.kind == "hold":
            return _hold(pc, pid, co, tick, step.reason)
        else:
            if procedure == "job" and step.name in ("rejected", "failed"):
                d.set_status(facts["job_id"], step.name)
            status = "cancelled" if step.name in DONE_CANCELLED else "done"
            _patch(pc, pid, status=status, comment=f"{step.name}. {step.reason}".strip())
            tick.ended = f"done:{step.name}"
            return tick
    return _hold(pc, pid, co, tick, f"no end after {MAX_STEPS} steps")


def _hank(cat: Catalog, repo: Path, step: Step, facts: dict) -> dict | None:
    """The refusal facts while a role is unpinned; None when the hank would run."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            render(cat, repo, step.name, Path(tmp) / "run", step.detail.get("tier", "everyday"))
        except HankRefused:
            return REFUSALS[step.name](facts)
    return None


def hank_issue(hank: str, issue: str) -> str:
    return f"hank:{hank}:{issue}"


def _hand_off(cat, d, pc, co, issue, pid, step: Step, facts: dict, tick: Tick) -> Tick:
    """A pinned hank goes to its role agent as a child issue that blocks this one."""
    pending = facts.get("_hank")
    if pending:
        tick.ended = f"wait:{pending['issue']}"
        return tick
    from kit.hankrun import agent_for

    child = hank_issue(step.name, issue)
    tier = step.detail.get("tier", "everyday")
    agent = agent_for(cat, step.name)
    ran_before = d.paperclip_id(child) is not None
    hid = ensure_issue(d, pc, co, child, parent=issue, assignee=agent)
    if ran_before:  # a second run of the hank (the strong tier, a re-run): its issue reopens
        _patch(pc, hid, status="todo", assigneeAgentId=co.id(agent), assigneeUserId=None)
    d.add_facts(
        issue,
        f"hand-off:{child}:{tier}:{facts.get('read_runs', 0)}",
        "dispatcher",
        {"_hank": {"name": step.name, "issue": child, "tier": tier}},
    )
    _patch(
        pc,
        pid,
        status="blocked",
        blockedByIssueIds=[hid],
        comment=f"{step.name} runs on its own issue; this one waits for it.",
    )
    tick.ended = f"wait:{child}"
    return tick


def finish_hank(
    d: Dossier,
    pc: Client,
    co: Company,
    issue: str,
    hank: str,
    key: str,
    fields: dict,
    source: str = "verify",
) -> None:
    """A hank run's verified facts (or its refusal's) to its work issue; the hank issue closes
    and the work issue goes back to the Dispatcher (Paperclip also wakes it when its blocker is
    done)."""
    _write(d, pc, co, issue, key, source, {**fields, "_hank": None})
    hid = d.paperclip_id(hank_issue(hank, issue))
    if hid:
        done = "Verified by kit verify; facts written."
        if source == "refusal":
            done = "Refused: the cautious facts are written; a person is asked on the route."
        _patch(pc, hid, status="done", comment=done)
    _patch(
        pc,
        ensure_issue(d, pc, co, issue),
        status="todo",
        blockedByIssueIds=[],
        assigneeAgentId=co.id("agent:dispatcher"),
        assigneeUserId=None,
    )


def refuse_held(d: Dossier, pc: Client, co: Company, issue: str, hank: str, held: HankHeld) -> None:
    """A hank whose cached answer may not stand as a model run's (an operator's on a real
    client's dossier; one of no recorded source anywhere) is refused the way an unpinned role
    is (P8): the hank's refusal facts (``REFUSALS``), with the reason
    as ``_hank_held``, go to the work issue, which goes back to the Dispatcher; its route goes
    on the cautious way (a read to the strong tier, a doubtful verdict to a person's card, a
    review contested, no close suggestion). Nothing of the cached answer becomes a fact."""
    held_facts = {"hank": hank, "roles": held.roles, "reason": held.reason}
    finish_hank(
        d,
        pc,
        co,
        issue,
        hank,
        f"held:{hank}:{','.join(held.roles)}:{held.input_hash[:16]}",
        {**REFUSALS[hank](d.facts(issue)), "_hank_held": held_facts},
        source="refusal",
    )


def _hold(pc: Client, pid: str, co: Company, tick: Tick, reason: str) -> Tick:
    """A person owns the issue now: assigned to the accountant, with the reason."""
    _patch(
        pc,
        pid,
        status="todo",
        assigneeUserId=co.accountant_user_id,
        assigneeAgentId=None,
        comment=f"Needs a person: {reason}",
    )
    tick.ended = f"hold: {reason}"
    return tick


def _question(d: Dossier, issue: str, step: Step, facts: dict) -> dict:
    """The question as asked: the route's detail, what the steps wrote for it, and what its
    check needs from the dossier now (``CONTEXT``)."""
    q = {"issue": issue, **step.detail, **facts.get(f"_ask:{step.name}", {})}
    if step.name in CONTEXT:
        q.update({k: v for k, v in CONTEXT[step.name](d, issue, facts).items() if v is not None})
    if step.name == "define_articol" and q.get("candidates"):
        q["choices"] = {"articol_id": list(q["candidates"])}
    return q


def _ask(cat, d, issue, pid, pc, co, step: Step, facts: dict, tick: Tick) -> Tick:
    kind = step.name
    question = _question(d, issue, step, facts)
    qhash = question_hash(question)
    if any(a["question_hash"] == qhash and a["outcome"] == "accepted" for a in d.answers(issue)):
        return _hold(pc, pid, co, tick, f"{kind} is answered; applying it is not wired yet")
    attempt = sum(1 for a in d.answers(issue) if a["question_hash"] == qhash)
    _open_card(cat, d, issue, pid, pc, co, kind, question, attempt, None)
    tick.ended = f"ask:{kind}"
    return tick


def _open_card(cat, d, issue, pid, pc, co, kind, question, attempt, error) -> None:
    saga = co.ids.get("agent:saga_import")
    body = card(cat, kind, issue, question, attempt, error, saga_agent_id=saga)
    out = pc.request("POST", f"/api/issues/{pid}/interactions", body)
    pending = {"id": out["id"], "kind": kind, "question": question, "attempt": attempt}
    d.add_facts(issue, f"card:{out['id']}", "dispatcher", {"_card": pending})
    _patch(pc, pid, status="in_review", comment=f"Waiting for the answer to {kind} on its card.")


def _take_answer(cat, d, issue, pid, pc, co, pending: dict, tick: Tick) -> bool:
    """True when the answer moved the facts and routing goes on."""
    rows = pc.request("GET", f"/api/issues/{pid}/interactions") or []
    rows = rows.get("interactions", rows) if isinstance(rows, dict) else rows
    inter = next((r for r in rows if r.get("id") == pending["id"]), None)
    kind, question = pending["kind"], pending["question"]
    if inter is None or inter.get("status") == "pending":
        tick.ended = f"wait:{kind}"
        return False
    row = cat.get("QuestionKind", kind)
    actor = "person" if row.actor == "accountant" else "saga_agent"
    who = inter.get("resolvedByUserId") or inter.get("resolvedByAgentId") or "unknown"
    try:
        if actor == "person" and not inter.get("resolvedByUserId"):
            raise CardError("a person's question was not answered by a person (P5)")
        answer = answer_from_result(cat, kind, question, inter)
    except CardError as exc:
        d.add_facts(issue, f"card-closed:{pending['id']}", "dispatcher", {"_card": None})
        _open_card(cat, d, issue, pid, pc, co, kind, question, pending["attempt"] + 1, str(exc))
        tick.steps.append(f"asked again: {exc}")
        tick.ended = f"ask:{kind}"
        return False
    if kind in LIVE_CONTEXT:  # checked against the dossier as it is now, not as it was asked
        question = {**question, **CONTEXT[kind](d, issue, d.facts(issue))}
    out = answer_question(cat, d, issue, kind, question, answer, who, actor)
    if out.status != "accepted":
        d.add_facts(issue, f"card-closed:{pending['id']}", "dispatcher", {"_card": None})
        _open_card(cat, d, issue, pid, pc, co, kind, question, pending["attempt"] + 1, out.error)
        tick.steps.append(f"asked again: {out.error}")
        tick.ended = f"ask:{kind}"
        return False
    effect = APPLY.get(kind)
    try:
        fields = effect(cat, d, issue, d.facts(issue), question, out.answer) if effect else {}
    except (StepError, StoreError) as exc:
        d.add_facts(issue, f"answer:{pending['id']}", "answer", {"_card": None})
        _hold(pc, pid, co, tick, f"{kind} is answered but cannot apply: {exc}")
        return False
    _write(d, pc, co, issue, f"answer:{pending['id']}", "answer", {**fields, "_card": None})
    tick.steps.append(f"answered:{kind}")
    if effect is None:
        _hold(pc, pid, co, tick, f"{kind} is answered; applying it is not wired yet")
        return False
    return True
