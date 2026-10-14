"""The five hanks and ``kit verify`` (WP-14): a model acts only in a codon, in a role the catalog
names, with one exact model pinned, and its file is checked before it is a fact (P8)."""

import json
from pathlib import Path

import jsonschema
import pytest

from kit.catalog import Catalog, CatalogError, load_catalog
from kit.cli import main
from kit.hanks import (
    DOUBTFUL,
    RUNTIME,
    UNPINNED,
    HankError,
    HankRefused,
    card_hash,
    check_hank,
    command,
    input_hash,
    render,
    roles_for,
    verify,
)
from kit.store import open_dossier

ROOT = Path(__file__).resolve().parents[1]
CLIENT, PARTNER, OTHER = "41526372", "73645193", "31415920"
HANKS = ["read-document", "split-container", "judge-document", "review-match", "close-suggest"]


@pytest.fixture(scope="module")
def cat():
    return load_catalog(ROOT / "catalog")


def pinned(cat: Catalog, **pins: str) -> Catalog:
    """The catalog with these roles pinned (role id = model id); the rest left as they are."""
    rows = {k: dict(v) for k, v in cat.rows.items()}
    for rid, model in pins.items():
        rows["ModelRole"][rid] = rows["ModelRole"][rid].model_copy(update={"model": model})
    return Catalog(rows=rows)


def all_pinned(cat: Catalog) -> Catalog:
    return pinned(cat, **{r: f"test-model-{i}" for i, r in enumerate(cat.ids("ModelRole"), 1)})


def out(body) -> bytes:
    return json.dumps(body).encode()


# ----- the hank folders -----


def test_every_hank_is_valid_for_the_pinned_runtime():
    schema = json.loads((ROOT / "hanks" / "schema" / "hank.schema.json").read_text())
    for h in HANKS:
        doc = json.loads((ROOT / "hanks" / h / "hank.json").read_text())
        jsonschema.validate(doc, schema)
        assert doc["$schema"] == f"https://unpkg.com/{RUNTIME}/schemas/hank.schema.json"


def test_the_schema_refuses_what_the_runtime_refuses():
    schema = json.loads((ROOT / "hanks" / "schema" / "hank.schema.json").read_text())
    doc = json.loads((ROOT / "hanks" / "review-match" / "hank.json").read_text())
    doc["hank"][0]["decides"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_the_hanks_are_the_roles_hanks(cat):
    folders = {p.name for p in (ROOT / "hanks").iterdir() if p.is_dir() and p.name != "schema"}
    roles = {cat.get("ModelRole", r).hank for r in cat.ids("ModelRole")}
    assert folders == roles == set(HANKS)
    for h in HANKS:
        assert check_hank(cat, ROOT, h) == [], h


def test_a_hank_that_drifts_from_its_roles_is_a_build_error(cat, tmp_path):
    import shutil

    shutil.copytree(ROOT / "hanks", tmp_path / "hanks")
    shutil.copytree(ROOT / "catalog", tmp_path / "catalog")
    path = tmp_path / "hanks" / "judge-document" / "hank.json"
    doc = json.loads(path.read_text())
    doc["hank"][0]["model"] = "test-model-1"
    doc["hank"][1]["continuationMode"] = "continue-previous"
    doc["hank"][1]["outputFiles"] = [{"copy": ["out/**/*"]}]
    path.write_text(json.dumps(doc))
    problems = check_hank(cat, tmp_path, "judge-document")
    assert any("the folder holds 'unpinned'" in p for p in problems)
    assert any("not fresh" in p for p in problems)
    assert any("copy only out/explain.json" in p for p in problems)
    with pytest.raises(HankError):
        render(all_pinned(cat), tmp_path, "judge-document", tmp_path / "run")


# ----- P8: one exact pin per role, or the hank refuses -----


@pytest.mark.law("P8")
def test_an_unpinned_role_refuses_and_nothing_is_written(cat, tmp_path):
    for h in HANKS:
        with pytest.raises(HankRefused) as refused:
            render(cat, ROOT, h, tmp_path / h)
        assert refused.value.roles and not (tmp_path / h).exists()
    one = pinned(cat, judge_document="test-model-1")  # its explainer is still unpinned
    with pytest.raises(HankRefused, match="explain_approve"):
        render(one, ROOT, "judge-document", tmp_path / "half")


@pytest.mark.law("P8")
def test_each_codon_runs_its_roles_pin_and_the_folder_stays_unpinned(cat, tmp_path):
    cat2 = all_pinned(cat)
    r = render(cat2, ROOT, "close-suggest", tmp_path / "run")
    doc = json.loads((r.run_dir / "hank.json").read_text())
    for c in doc["hank"]:
        assert c["model"] == cat2.get("ModelRole", r.roles[c["id"]]).model
    assert (r.run_dir / "prompts" / "suggest.md").is_file()
    assert (
        json.loads((ROOT / "hanks" / "close-suggest" / "hank.json").read_text())["hank"][0]["model"]
        == UNPINNED
    )
    with pytest.raises(HankError, match="written once"):
        render(cat2, ROOT, "close-suggest", tmp_path / "run")


@pytest.mark.law("P8")
def test_the_strong_read_is_its_own_role(cat, tmp_path):
    cat2 = pinned(cat, reader_document="test-model-1", reader_document_strong="test-model-9")
    assert roles_for(cat2, "read-document", "strong")["read"].id == "reader_document_strong"
    every = render(cat2, ROOT, "read-document", tmp_path / "a")
    strong = render(cat2, ROOT, "read-document", tmp_path / "b", tier="strong")
    assert every.models == {"read": "test-model-1"} and strong.models == {"read": "test-model-9"}


@pytest.mark.law("P8")
@pytest.mark.parametrize(
    "model", ["sonnet", "opus", "auto", "claude-3-7-sonnet-latest", "Claude-x-1", "gpt"]
)
def test_a_pin_is_an_exact_model_id(tmp_path, model):
    import shutil

    shutil.copytree(ROOT / "catalog", tmp_path / "catalog")
    path = tmp_path / "catalog" / "50_control" / "model_roles.yaml"
    text = path.read_text().replace(
        "    codon: judge\n", f"    codon: judge\n    model: {model}\n", 1
    )
    path.write_text(text)
    with pytest.raises(CatalogError, match="not an exact model id"):
        load_catalog(tmp_path / "catalog")


@pytest.mark.law("P8")
def test_the_runtime_is_started_one_way(cat, tmp_path):
    r = render(all_pinned(cat), ROOT, "review-match", tmp_path / "run")
    argv = command(r, tmp_path / "data", tmp_path / "out")
    assert argv[:2] == ["bunx", RUNTIME] and "--headless" in argv
    assert argv[argv.index("--max-cost") + 1] == "0.10"
    assert argv[argv.index("--max-time") + 1] == "180"
    assert not {"-m", "--model", "--ignore-rig-failures", "--force"} & set(argv)
    with pytest.raises(HankError, match="never passed"):
        command(r, Path("--model"), tmp_path / "out")


def test_the_card_hash_moves_with_the_pin_the_card_and_the_system_prompt(cat, tmp_path):
    import shutil

    role = cat.get("ModelRole", "judge_document")
    base = card_hash(ROOT, role)
    assert card_hash(ROOT, role.model_copy(update={"model": "test-model-1"})) != base
    shutil.copytree(ROOT / "hanks", tmp_path / "hanks")
    (tmp_path / "hanks" / "judge-document" / "prompts" / "system.md").write_text("changed")
    assert card_hash(tmp_path, role) != base
    assert input_hash({"a": 1, "b": 2}) == input_hash({"b": 2, "a": 1})


# ----- kit verify: the file is checked before it is a fact -----


@pytest.mark.law("P8", "P10")
def test_a_file_that_misses_its_shape_is_refused(cat):
    good = {"accounts_ok": True, "risk": "low", "needs_human": False}
    assert verify(cat, "judge_document", {}, out(good)).ok
    for bad in (
        out({**good, "post_it": True}),
        out({**good, "risk": "none"}),
        out({"accounts_ok": True}),
        b"not json",
        None,
    ):
        v = verify(cat, "judge_document", {}, bad)
        assert not v.ok and v.problems
        assert v.body == DOUBTFUL  # a refused judge reads as the doubtful verdict: it asks
    v = verify(cat, "review_match", {"job_id": "j_1"}, out({"job_id": "j_1"}))
    assert not v.ok and v.body is None


def statement(**kw):
    s = {
        "holder_cui": CLIENT,
        "iban": "RO49AAAA1B31007593840000",
        "currency": "RON",
        "period_from": "2026-09-01",
        "period_to": "2026-09-30",
        "opening": "1000.00",
        "closing": "1150.00",
        "lines": [
            {"date": "2026-09-03", "description": "incasare", "debit": "0.00", "credit": "250.00"},
            {
                "date": "2026-09-04",
                "description": "plata furnizor",
                "debit": "100.00",
                "credit": "0.00",
                "counterparty": PARTNER,
            },
        ],
    }
    return {"doc_type": "statement", "statement": {**s, **kw}, "invoice": None}


def test_a_statement_read_must_tie_and_be_the_clients(cat):
    inp = {"client_cui": f"RO{CLIENT}", "expected": "statement"}
    assert verify(cat, "reader_document", inp, out(statement())).ok
    assert verify(cat, "reader_document_strong", inp, out(statement())).ok
    cases = {
        "do not tie": statement(closing="1150.01"),
        "not the client": statement(holder_cui=OTHER),
        "not an amount": statement(opening="1.000,00"),
        "not a date": statement(period_to="30.09.2026"),
    }
    for why, body in cases.items():
        v = verify(cat, "reader_document", inp, out(body))
        assert not v.ok and any(why in p for p in v.problems), (why, v.problems)
    invoice = {"doc_type": "invoice", "statement": None, "invoice": None}
    assert not verify(cat, "reader_document", inp, out(invoice)).ok


def test_an_invoice_read_must_add_up_and_name_the_client_once(cat):
    inv = {
        "number": "F-1",
        "date": "2026-09-10",
        "seller_cui": PARTNER,
        "buyer_cui": CLIENT,
        "currency": "RON",
        "net": "100.00",
        "vat": "21.00",
        "gross": "121.00",
    }
    inp = {"client_cui": CLIENT, "expected": None}
    body = {"doc_type": "invoice", "statement": None, "invoice": inv}
    assert verify(cat, "reader_document", inp, out(body)).ok
    off = {**body, "invoice": {**inv, "gross": "121.01"}}
    assert "not the gross" in verify(cat, "reader_document", inp, out(off)).problems[0]
    neither = {**body, "invoice": {**inv, "buyer_cui": OTHER}}
    assert any(
        "exactly one" in p for p in verify(cat, "reader_document", inp, out(neither)).problems
    )
    expected = {"client_cui": CLIENT, "expected": "statement"}
    assert not verify(cat, "reader_document", expected, out(body)).ok


def test_proposed_parts_are_files_of_the_container(cat):
    h1, h2 = "a" * 64, "b" * 64
    inp = {
        "pack": {
            "client_cui": CLIENT,
            "period": "2026-09",
            "source_hash": "c" * 64,
            "source_doc_id": "decont_cheltuieli",
            "kinds": ["xlsx"],
            "identity_ok": True,
        },
        "files": [{"part_hash": h1, "name": "f1.xml"}],
        "source_docs": ["ro_efactura_ubl"],
    }
    part = {"part_hash": h1, "source_doc_id": "ro_efactura_ubl", "kinds": ["ubl_spv"]}
    assert verify(cat, "reader_split", inp, out({"parts": [part]})).ok
    stray = {"parts": [part, {**part, "part_hash": h2}]}
    assert any("not a file" in p for p in verify(cat, "reader_split", inp, out(stray)).problems)
    other = {"parts": [{**part, "source_doc_id": "bon_fiscal"}]}
    assert not verify(cat, "reader_split", inp, out(other)).ok


def test_an_explanation_cites_only_what_the_input_holds(cat):
    inp = {"facts": {"document.gross": "121.00", "articol": "ro_efactura_inbound"}}
    body = {
        "explanation": "Factura de 121.00 lei.",
        "facts_cited": ["document.gross", "verdict.risk"],
        "missing": [],
    }
    assert verify(cat, "explain_approve", inp, out(body)).ok
    invented = {**body, "facts_cited": ["partner.history"]}
    assert not verify(cat, "explain_approve", inp, out(invented)).ok
    assert not verify(cat, "explain_close", inp, out(body)).ok  # verdict.* is the judge's
    long = {**body, "explanation": "x" * 1201}
    assert not verify(cat, "explain_approve", inp, out(long)).ok


def test_a_review_keeps_its_job_and_cannot_flip_to_posted(cat):
    inp = {"job_id": "j_1"}
    ok = {"job_id": "j_1", "decision": "contest", "reason": "partener diferit"}
    assert verify(cat, "review_match", inp, out(ok)).ok
    assert not verify(cat, "review_match", inp, out({**ok, "job_id": "j_2"})).ok
    assert not verify(cat, "review_match", inp, out({**ok, "decision": "already_posted"})).ok


@pytest.mark.law("P11")
def test_a_suggestion_never_files_a_material_month(cat):
    body = {"action": "file", "books_support_declaration": True, "reason": "totul se leaga"}
    clean = verify(cat, "close_suggest", {"material": False}, out(body))
    assert clean.ok and clean.body["action"] == "file"
    material = verify(cat, "close_suggest", {"material": True}, out(body))
    assert material.ok and material.body["action"] == "hold"
    assert material.body["books_support_declaration"] is False
    unsaid = verify(cat, "close_suggest", {}, out(body))  # no materiality given: material
    assert unsaid.body["action"] == "hold"


def test_a_drafted_rule_must_explain_an_unexplained_document(cat):
    inp = {
        "unexplained": [
            {
                "saga_key": "X-1",
                "doc_class": "intrare",
                "number": "CHR-9",
                "date": "2026-09-25",
                "partner_cui": PARTNER,
                "gross": "50.00",
                "validated": True,
                "accounts": ["401", "612"],
            }
        ]
    }
    rule = {"rule_id": "chirie", "kind": "document", "partner_cui": PARTNER, "number_prefix": "CHR"}
    assert verify(cat, "draft_rule", inp, out({"rules": [rule]})).ok
    assert verify(cat, "draft_rule", inp, out({"rules": []})).ok
    line = {"rule_id": "chirie_612", "kind": "line", "account": "612"}
    assert verify(cat, "draft_rule", inp, out({"rules": [line]})).ok
    misses = [
        {**rule, "partner_cui": OTHER},
        {"rule_id": "fara_cont", "kind": "line"},
        {**rule, "account": "612"},
        {**line, "account": "999"},
    ]
    for bad in misses:
        assert not verify(cat, "draft_rule", inp, out({"rules": [bad]})).ok, bad
    assert not verify(cat, "draft_rule", inp, out({"rules": [rule, rule]})).ok


def test_an_unknown_role_is_an_error(cat):
    with pytest.raises(CatalogError):
        verify(cat, "auditor", {}, out({}))


# ----- the commands -----


def test_hank_command(tmp_path, capsys):
    assert main(["hank", "check", "--root", str(ROOT), "--catalog", str(ROOT / "catalog")]) == 0
    assert "judge-document ok" in capsys.readouterr().out
    run = ["hank", "render", "judge-document", "--run", str(tmp_path / "run")]
    assert main([*run, "--root", str(ROOT), "--catalog", str(ROOT / "catalog")]) == 3
    assert "refused" in capsys.readouterr().err and not (tmp_path / "run").exists()


def test_verify_command_stores_a_passing_answer(tmp_path, capsys):
    (tmp_path / "input.json").write_text(json.dumps({"job_id": "j_1"}))
    (tmp_path / "review.json").write_text(
        json.dumps({"job_id": "j_1", "decision": "confirm", "reason": "aceleasi chei"})
    )
    args = ["verify", "--role", "review_match", "--input", str(tmp_path / "input.json")]
    common = ["--root", str(ROOT), "--catalog", str(ROOT / "catalog")]
    stored = ["--dossiers", str(tmp_path / "d"), "--cui", CLIENT]
    assert main([*args, "--output", str(tmp_path / "review.json"), *stored, *common]) == 0
    assert json.loads(capsys.readouterr().out)["stored"] is True
    d = open_dossier(tmp_path / "d", CLIENT)
    role = load_catalog(ROOT / "catalog").get("ModelRole", "review_match")
    key = (input_hash({"job_id": "j_1"}), card_hash(ROOT, role))
    assert d.model_answer("review_match", *key)["decision"] == "confirm"
    assert main([*args, "--output", str(tmp_path / "missing.json"), *common]) == 1
    assert "was not written" in capsys.readouterr().out
