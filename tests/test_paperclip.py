"""Paperclip (WP-15): the company set-up, question cards (D2) and the Dispatcher's wake."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fake_paperclip import Fake  # noqa: E402

from kit.cards import PROMPTS, CardError, answer_from_result, card
from kit.catalog import load_catalog
from kit.cli import main
from kit.dispatch import Company, dispatch
from kit.hanks import DOUBTFUL
from kit.paperclip import (
    HttpClient,
    PaperclipError,
    SetupError,
    apply,
    load_company,
    plan_client,
    plan_company,
)
from kit.questions import parse_type
from kit.store import open_dossier

ROOT = Path(__file__).resolve().parents[1]
CLIENT = "41526372"
ENV = {
    "KIT_HOME": "/srv/kit",
    "DOSSIERS": "/srv/dossiers",
    "SAGA_AGENT_URL": "https://saga.example.invalid/hook",
    "ACCOUNTANT_USER_ID": "user-acc",
}
SAGA = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def company() -> Company:
    ids = {
        "company": "co-1",
        f"project:{CLIENT}": "prj-1",
        "agent:dispatcher": "agt-d",
        "agent:saga_import": SAGA,
        **{f"label:{n}": f"lbl-{n}" for n in ("batch", "job", "recon", "close")},
    }
    return Company(ids, "user-acc")


def job_issue(d, **facts) -> str:
    job, _ = d.insert_job(CLIENT, "a" * 64, "ro_efactura", "ro_efactura_ubl", "2026-09")
    issue = f"job:{job.job_id}"
    base = dict(
        job_id=job.job_id,
        status="bound",
        has_xml=True,
        extracted=True,
        candidates=["ro_efactura_inbound"],
        bound_articol="ro_efactura_inbound",
        pre_verdict="absent",
        policy="first_n",
        first_n=5,
        book_is_saga=True,
        mouths_for_class=1,
    )
    seeded = {**base, **facts}
    chain = ["bound", "reconcile_pre", "approved", "packaged", "wait_validare", "acked"]
    if seeded["status"] in chain:
        stop = chain.index(seeded["status"])
        if seeded.get("pre_verdict") and stop < 1:
            stop = 1
        for st in chain[: stop + 1]:
            d.set_status(job.job_id, st)
    d.add_facts(issue, "seed", "kit", seeded)
    return issue


def answered(**answers) -> dict:
    out = []
    for q, v in answers.items():
        if isinstance(v, list):
            out.append({"questionId": q, "optionIds": v})
        else:
            out.append({"questionId": q, "optionIds": [], "otherText": v})
    return {"version": 1, "answers": out}


# ----- cards (D2) -----


def test_every_question_kind_has_a_card_and_every_field_a_prompt(cat):
    for kind in cat.ids("QuestionKind"):
        row = cat.get("QuestionKind", kind)
        c = card(cat, kind, "job:j_1", {"issue": "job:j_1"}, saga_agent_id=SAGA)
        assert c["kind"] == "ask_user_questions" and len(c["idempotencyKey"]) <= 255
        qs = c["payload"]["questionSet"]["questions"]
        assert [q["id"] for q in qs] == list(row.answer)
        for q in qs:
            assert (kind, q["id"]) in PROMPTS
            assert q["required"] == (not parse_type(row.answer[q["id"]]).optional)
            if q["answerMode"] == "text":
                assert "options" not in q
            else:
                assert len(q["options"]) >= 2 and len({o["id"] for o in q["options"]}) == len(
                    q["options"]
                )


@pytest.mark.law("P5")
def test_a_persons_card_is_human_only_and_the_saga_agents_is_addressed(cat):
    person = card(cat, "v2_close", "close:1:2026-09", {"material": True})
    assert person["resolverPolicy"] == "human_only" and "addresseeAgentId" not in person
    saga = card(cat, "wait_validare", "job:j_1", {}, saga_agent_id=SAGA)
    assert saga["addresseeAgentId"] == SAGA and "resolverPolicy" not in saga
    with pytest.raises(CardError, match="SAGA agent"):
        card(cat, "wait_validare", "job:j_1", {})


@pytest.mark.law("P9")
def test_the_same_question_is_one_card_and_a_refusal_a_new_one(cat):
    q = {"material": True, "blockers": ["c1"]}
    a, b = card(cat, "v2_close", "close:1:2026-09", q), card(cat, "v2_close", "close:1:2026-09", q)
    assert a["idempotencyKey"] == b["idempotencyKey"]
    again = card(cat, "v2_close", "close:1:2026-09", q, attempt=1, error="cannot file")
    assert again["idempotencyKey"] != a["idempotencyKey"]
    assert "cannot file" in again["payload"]["questionSet"]["description"]


def test_answers_come_back_in_the_kinds_shape(cat):
    def back(kind, result, question=None, status="answered"):
        return answer_from_result(
            cat,
            kind,
            question or {},
            {"kind": "ask_user_questions", "status": status, "result": result},
        )

    assert back("v2_close", answered(action=["hold"])) == {"action": "hold"}
    assert back("v2_close", answered(action=["patch_maps"], explained_rule="chirie")) == {
        "action": "patch_maps",
        "explained_rule": "chirie",
    }
    edit = back("v3_approve", answered(decision=["edit"], edit='{"net": "100.00"}'))
    assert edit == {"decision": "edit", "edit": {"net": "100.00"}}
    assert back("wait_validare", answered(validated=["true"], saga_doc_key="I-7")) == {
        "validated": True,
        "saga_doc_key": "I-7",
    }
    ambiguous = back(
        "recon_ambiguous",
        answered(action=["already_posted"], sink_line_ids=["0", "2"]),
        {"choices": {"sink_line_ids": [0, 1, 2]}},
    )
    assert ambiguous == {"action": "already_posted", "sink_line_ids": [0, 2]}
    for bad in (
        answered(action=["hold"], post_it="yes"),  # a question the card did not ask
        answered(decision=["edit"], edit="{not json"),
    ):
        with pytest.raises(CardError):
            back("v3_approve" if "decision" in json.dumps(bad) else "v2_close", bad)
    for status in ("pending", "expired", "cancelled"):
        with pytest.raises(CardError, match="not answered"):
            back("v2_close", answered(action=["hold"]), status=status)


def test_a_decont_is_split_by_ticking_the_proposed_parts(cat):
    parts = [
        {
            "part_hash": "a" * 64,
            "source_doc_id": "ro_efactura_ubl",
            "kinds": ["ubl_spv"],
            "name": "f1",
        },
        {"part_hash": "b" * 64, "source_doc_id": "bon_fiscal", "kinds": ["jpg"], "name": "b1"},
    ]
    q = {"proposed": {"parts": parts}}
    c = card(cat, "decont_split", "batch:b1", q)
    assert c["kind"] == "request_checkbox_confirmation"
    assert "defaultSelectedOptionIds" not in c["payload"]  # nothing preselected
    inter = {
        "kind": c["kind"],
        "status": "accepted",
        "result": {"version": 1, "outcome": "accepted", "selectedOptionIds": ["a" * 64]},
    }
    got = answer_from_result(cat, "decont_split", q, inter)
    assert got == {"parts": [{k: v for k, v in parts[0].items() if k != "name"}]}
    rejected = {
        "kind": c["kind"],
        "status": "rejected",
        "result": {"version": 1, "outcome": "rejected", "reason": "lipsește o factură"},
    }
    with pytest.raises(CardError, match="lipsește"):
        answer_from_result(cat, "decont_split", q, rejected)
    assert card(cat, "decont_split", "batch:b1", {})["kind"] == "ask_user_questions"


# ----- the company set-up -----


def test_the_company_file_needs_its_environment():
    with pytest.raises(SetupError, match="ACCOUNTANT_USER_ID"):
        load_company(ROOT / "paperclip" / "company.yaml", env={})


def test_the_company_plan(tmp_path):
    conf = load_company(ROOT / "paperclip" / "company.yaml", env=ENV)
    plan = plan_company(conf)
    refs = [r.ref for r in plan.requests if r.ref]
    assert refs[:2] == ["company", "goal"]
    assert {"agent:dispatcher", "agent:reader", "agent:classifier", "agent:saga_import"} <= set(
        refs
    )
    budgets = [r.body for r in plan.requests if r.path.endswith("/budgets/policies")]
    assert len(budgets) == 5 and all(b["hardStopEnabled"] for b in budgets)
    dispatcher = next(r.body for r in plan.requests if r.ref == "agent:dispatcher")
    assert dispatcher["adapterType"] == "process"
    assert dispatcher["adapterConfig"]["args"] == ["run", "kit", "dispatch"]
    assert dispatcher["adapterConfig"]["cwd"] == "/srv/kit"
    assert any(r.path == "/api/agents/{agent:saga_import}/pause" for r in plan.requests)


def test_a_model_is_never_pinned_on_a_paperclip_agent(tmp_path):
    text = (ROOT / "paperclip" / "company.yaml").read_text()
    bad = text.replace("timeoutSec: 600", "timeoutSec: 600\n      model: claude-x-1")
    (tmp_path / "c.yaml").write_text(bad)
    with pytest.raises(SetupError, match="pinned per role in the catalog"):
        load_company(tmp_path / "c.yaml", env=ENV)


def test_a_client_is_its_project_budget_and_routines():
    conf = load_company(ROOT / "paperclip" / "company.yaml", env=ENV)
    plan = plan_client(conf, f"RO{CLIENT}", monthly_cents=5000)
    routines = [r for r in plan.requests if r.path.endswith("/routines")]
    assert {r.body["assigneeAgentId"] for r in routines} == {
        "{agent:dispatcher}",
        "{agent:saga_import}",
    }
    assert all(r.body["projectId"] == f"{{project:{CLIENT}}}" for r in routines)
    triggers = [r.body for r in plan.requests if r.path.endswith("/triggers")]
    assert {t["kind"] for t in triggers} == {"webhook", "schedule"}
    with pytest.raises(SetupError, match="check digit"):
        plan_client(conf, "41526373")


class FailOnce(Fake):
    def __init__(self, at: int, status: int):
        super().__init__()
        self.at, self.status = at, status

    def request(self, method, path, body=None):
        if len(self.calls) == self.at:
            self.calls.append(("FAILED", path, body))
            raise PaperclipError(self.status, method, path, "no")
        return super().request(method, path, body)


@pytest.mark.law("P9")
def test_apply_creates_once_and_resumes_after_a_refusal(tmp_path):
    conf = load_company(ROOT / "paperclip" / "company.yaml", env=ENV)
    plan = plan_company(conf)
    state = tmp_path / "state.json"
    refused = FailOnce(at=5, status=422)  # refused: the server did nothing
    with pytest.raises(PaperclipError):
        apply(plan, refused, state)
    fake = Fake()
    ids = apply(plan, fake, state)
    assert len(refused.calls) - 1 + len(fake.calls) == len(plan.requests)
    sent = json.dumps([c[1] for c in fake.calls] + [c[2] for c in fake.calls])
    assert not re.search(r"\{[a-z][a-z0-9_:]*\}", sent)  # every ref resolved
    assert set(ids) >= {"company", "agent:dispatcher", "project:build"}
    again = Fake()
    apply(plan, again, state)
    assert again.calls == []


@pytest.mark.law("P9")
def test_a_run_that_stopped_mid_request_is_never_resent_blind(tmp_path):
    conf = load_company(ROOT / "paperclip" / "company.yaml", env=ENV)
    plan = plan_company(conf)
    state = tmp_path / "state.json"
    with pytest.raises(PaperclipError):
        apply(plan, FailOnce(at=3, status=502), state)  # the server may have acted
    with pytest.raises(SetupError, match="stopped during label:job"):
        apply(plan, Fake(), state)
    body = json.loads(state.read_text())
    body["ids"]["label:job"] = "lbl-found-by-a-person"
    del body["inflight"]
    state.write_text(json.dumps(body))
    rest = Fake()
    ids = apply(plan, rest, state)
    assert ids["label:job"] == "lbl-found-by-a-person"
    assert not any(c[2] and c[2].get("name") == "job" for c in rest.calls)


def test_nested_ids_and_a_webhook_secret_kept_apart(tmp_path):
    class Triggers(Fake):
        def request(self, method, path, body=None):
            self.calls.append((method, path, body))
            if path.endswith("/triggers") and body["kind"] == "webhook":
                return {
                    "trigger": {"id": "trg-1"},
                    "secretMaterial": {"webhookUrl": "http://h/fire/x", "webhookSecret": "s3"},
                }
            if path.endswith("/triggers"):
                return {"trigger": {"id": self._id("trg")}}
            return {"id": self._id("obj")}

    conf = load_company(ROOT / "paperclip" / "company.yaml", env=ENV)
    state = tmp_path / "state.json"
    ids = {"company": "co-1", **{f"agent:{a}": f"agt-{a}" for a in conf["agents"]}}
    state.write_text(json.dumps({"ids": ids, "sent": []}))
    out = apply(plan_client(conf, CLIENT), Triggers(), state)
    assert out[f"trigger:{CLIENT}:recon_recheck"] == "trg-1"
    assert out[f"trigger:{CLIENT}:recon_recheck:url"] == "http://h/fire/x"
    assert "s3" not in state.read_text()
    secrets = tmp_path / "state.secrets.json"
    assert (
        json.loads(secrets.read_text())[f"trigger:{CLIENT}:recon_recheck"]["webhookSecret"] == "s3"
    )
    assert (secrets.stat().st_mode & 0o777) == 0o600


def test_the_http_client_speaks_bearer_json():
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers["Authorization"]
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code = 409 if self.path.endswith("/checkout") else 201
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b'{"id": "x1"}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = HttpClient(f"http://127.0.0.1:{srv.server_port}", "k-123")
        assert c.request("POST", "/api/companies", {"name": "n"}) == {"id": "x1"}
        assert seen == {"auth": "Bearer k-123", "body": {"name": "n"}}
        with pytest.raises(PaperclipError, match="409"):
            c.request("POST", "/api/issues/i/checkout", {})
        with pytest.raises(SetupError, match="under /api"):
            c.request("GET", "/admin")
    finally:
        srv.shutdown()


# ----- the Dispatcher -----


@pytest.mark.law("P8", "P12")
def test_a_job_is_judged_by_refusal_asked_and_held_after_the_answer(cat, tmp_path):
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    issue = job_issue(d)
    tick = dispatch(cat, ROOT, d, issue, pc, co)
    assert tick.steps == ["hank:judge-document", "ask:v3_approve"]
    assert d.facts(issue)["verdict"] == DOUBTFUL
    pid = d.paperclip_id(issue)
    assert pc.issues[pid]["title"] == f"{issue} [{CLIENT}]"
    assert pc.issues[pid]["status"] == "in_review" and len(pc.cards[pid]) == 1
    assert pc.cards[pid][0]["resolverPolicy"] == "human_only"
    assert any("no pinned model" in c for c in pc.comments[pid])

    replay = dispatch(cat, ROOT, d, issue, pc, co)  # nothing answered yet: nothing new
    assert replay.ended == "wait:v3_approve" and len(pc.cards[pid]) == 1

    pc.resolve(pid, "answered", answered(decision=["approve"]))
    after = dispatch(cat, ROOT, d, issue, pc, co)
    assert after.steps[:2] == ["answered:v3_approve", "kit:package"]
    assert (
        after.ended
        == "hold: kit step package: the package is WP-10's: the SAGA XML renderer waits on R4"
    )
    assert (
        pc.issues[pid]["assigneeUserId"] == "user-acc" and pc.issues[pid]["assigneeAgentId"] is None
    )
    log = d.answers(issue)
    assert log[-1]["outcome"] == "accepted" and log[-1]["operator"] == "user-acc"


@pytest.mark.law("P5")
def test_a_persons_card_resolved_by_an_agent_is_asked_again(cat, tmp_path):
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    issue = job_issue(d)
    dispatch(cat, ROOT, d, issue, pc, co)
    pid = d.paperclip_id(issue)
    pc.resolve(pid, "answered", answered(decision=["approve"]), user=None, agent="agt-x")
    tick = dispatch(cat, ROOT, d, issue, pc, co)
    assert "not answered by a person" in tick.steps[0] and len(pc.cards[pid]) == 2
    assert "approval" not in d.facts(issue)


@pytest.mark.law("P11")
def test_file_on_a_material_month_is_refused_on_the_card_and_asked_again(cat, tmp_path):
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    issue = f"close:{CLIENT}:2026-09"
    ctx = {"material": True, "blockers": ["c1_outbound_complete: holes"]}
    d.add_facts(
        issue,
        "seed",
        "kit",
        {"locked": True, "diffed": True, "suggested": True, "_ask:v2_close": ctx},
    )
    assert dispatch(cat, ROOT, d, issue, pc, co).ended == "ask:v2_close"
    pid = d.paperclip_id(issue)
    pc.resolve(pid, "answered", answered(action=["file"]))
    again = dispatch(cat, ROOT, d, issue, pc, co)
    assert "cannot file" in again.steps[0] and len(pc.cards[pid]) == 2
    assert "cannot file" in pc.cards[pid][1]["payload"]["questionSet"]["description"]
    pc.resolve(pid, "answered", answered(action=["hold"]))
    held = dispatch(cat, ROOT, d, issue, pc, co)
    assert held.steps == ["answered:v2_close", "hold:hold"]
    assert d.facts(issue)["v2"] == "hold"


def test_an_uploaded_export_settles_need_rj_export_and_the_window_is_rechecked(cat, tmp_path):
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    issue = f"recon:{CLIENT}:2026-09"
    d.put_export("rj_aug", ["2026-08"], {"covered": ["2026-08"]})
    d.add_facts(
        issue,
        "seed",
        "kit",
        {
            "checked": True,
            "missing_months": ["2026-08"],
            "_ask:need_rj_export": {"exports": {"rj_aug": ["2026-08"]}},
        },
    )
    dispatch(cat, ROOT, d, issue, pc, co)
    pid = d.paperclip_id(issue)
    pc.resolve(pid, "answered", answered(export_id="rj_aug"))
    tick = dispatch(cat, ROOT, d, issue, pc, co)
    assert tick.steps == ["answered:need_rj_export", "kit:recheck_window", "done:clear"]


def test_an_answer_whose_effect_is_not_wired_is_held_never_asked_twice(cat, tmp_path, monkeypatch):
    import kit.dispatch

    monkeypatch.setattr(kit.dispatch, "APPLY", {})
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    issue = f"close:{CLIENT}:2026-09"
    d.add_facts(
        issue,
        "seed",
        "kit",
        {"locked": True, "diffed": True, "suggested": True, "_ask:v2_close": {"material": False}},
    )
    dispatch(cat, ROOT, d, issue, pc, co)
    pid = d.paperclip_id(issue)
    pc.resolve(pid, "answered", answered(action=["hold"]))
    first = dispatch(cat, ROOT, d, issue, pc, co)
    assert first.ended.startswith("hold: v2_close is answered")
    second = dispatch(cat, ROOT, d, issue, pc, co)
    assert second.ended.startswith("hold: v2_close is answered") and len(pc.cards[pid]) == 1


def test_bind_runs_from_the_facts_and_a_missing_executor_holds(cat, tmp_path):
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    issue = job_issue(
        d,
        status="ingested",
        bound_articol=None,
        pre_verdict=None,
        policy="always",
        first_n=None,
        mouths_for_class=0,
        _doc_class="intrare",
    )
    tick = dispatch(cat, ROOT, d, issue, pc, co)
    assert tick.steps == ["kit:bind", "kit:pre_check"]
    assert tick.ended == "hold: kit step pre_check: the fact '_doc' is not established yet"
    f = d.facts(issue)
    assert f["bound_articol"] == "ro_efactura_inbound" and f["mouths_for_class"] == 1
    assert d.job(issue.split(":", 1)[1]).status == "bound"


def test_a_refused_review_is_a_contest_and_terminal_routes_close_the_issue(cat, tmp_path):
    d, pc, co = open_dossier(tmp_path, CLIENT), Fake(), company()
    recon = f"recon:{CLIENT}:2026-09"
    d.add_facts(recon, "seed", "kit", {"checked": True, "to_review": ["j_1"]})
    tick = dispatch(cat, ROOT, d, recon, pc, co)
    assert tick.steps == ["hank:review-match", "ask:recon_review_contest"]
    assert d.facts(recon)["contested"] == ["j_1"]
    done = job_issue(d, status="acked")
    assert dispatch(cat, ROOT, d, done, pc, co).ended == "done:acked"
    assert pc.issues[d.paperclip_id(done)]["status"] == "done"


def test_dispatch_command_refuses_without_its_environment(monkeypatch, capsys):
    for k in ("POARTA_DOSSIERS", "POARTA_PAPERCLIP_STATE", "PAPERCLIP_TASK_ID"):
        monkeypatch.delenv(k, raising=False)
    assert main(["dispatch"]) == 1
    assert "kit dispatch" in capsys.readouterr().err


def test_setup_command_prints_the_plan(monkeypatch, capsys):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert main(["paperclip", "setup", "--file", str(ROOT / "paperclip" / "company.yaml")]) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[0])
    assert first["ref"] == "company" and first["path"] == "/api/companies"
