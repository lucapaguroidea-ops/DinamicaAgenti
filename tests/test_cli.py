"""The CLI: built commands work, planned ones refuse instead of pretending."""

from pathlib import Path

import pytest

from kit.cli import PLANNED, main


def test_cui_command(capsys):
    assert main(["cui", "RO41526372"]) == 0
    assert "41526372 valid" in capsys.readouterr().out
    assert main(["cui", "41526371"]) == 1


def test_planned_commands_refuse(capsys):
    for name in PLANNED:
        assert main([name]) == 2
        assert "not built yet" in capsys.readouterr().err


def test_every_command_the_documents_name_exists():
    import re
    from pathlib import Path

    import pytest

    root = Path(__file__).resolve().parents[1]
    named = set()
    for doc in [*root.glob("*.md"), *root.glob("*/README.md")]:
        named |= set(
            re.findall(r"`(?:uv run )?kit ([a-z][a-z-]*)", doc.read_text(encoding="utf-8"))
        )
    assert named, "the documents name kit commands"
    for name in sorted(named):
        with pytest.raises(SystemExit) as out:
            main([name, "--help"])
        assert out.value.code == 0, name


def test_catalog_command(tmp_path, capsys):
    assert main(["catalog"]) == 0
    assert "Articol" in capsys.readouterr().out
    (tmp_path / "bad.yaml").write_text("catalog: Ledger\nfile_schema: 1\nrows: []\n")
    assert main(["catalog", str(tmp_path)]) == 1
    assert "unknown catalog 'Ledger'" in capsys.readouterr().err


def test_emit_command(tmp_path, capsys):
    import hashlib
    import json

    good = {
        "client_cui": "41526372",
        "period": "2026-09",
        "source_hash": hashlib.sha256(b"doc").hexdigest(),
        "source_doc_id": "ro_efactura_ubl",
        "kinds": ["ubl_spv"],
        "our_role": "inbound",
        "counterparty_cui": "73645193",
    }
    (tmp_path / "pack.json").write_text(json.dumps(good))
    assert main(["emit", str(tmp_path / "pack.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["emit"] and out["job_kind"] == "ro_efactura"

    (tmp_path / "bad.json").write_text(json.dumps({**good, "client_cui": "41526371"}))
    assert main(["emit", str(tmp_path / "bad.json")]) == 1
    assert "not a valid CUI" in capsys.readouterr().err


def test_read_command(tmp_path, capsys):
    import io
    import json
    import zipfile

    from test_ubl import ubl

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("123.xml", ubl())
        z.writestr("semnatura_123.xml", b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/>')
    (tmp_path / "spv.zip").write_bytes(buf.getvalue())
    assert main(["read", str(tmp_path / "spv.zip"), "--client", "RO41526372"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["file"] == "123.xml" and out["client"]["our_role"] == "inbound"
    assert out["document"]["totals"]["gross"] == "119.00"

    (tmp_path / "bad.xml").write_bytes(ubl(payable="1.00"))
    assert main(["read", str(tmp_path / "bad.xml")]) == 1
    assert "BR-CO-16" in capsys.readouterr().err


def _emit_pack(**kw) -> dict:
    import hashlib

    base = {
        "client_cui": "41526372",
        "period": "2026-09",
        "source_hash": hashlib.sha256(b"doc").hexdigest(),
        "source_doc_id": "ro_efactura_ubl",
        "kinds": ["ubl_spv"],
        "our_role": "inbound",
        "counterparty_cui": "73645193",
    }
    return {**base, **kw}


def _dossier_rows(root) -> dict:
    """Every table of the client's dossier, row by row: what an emit must not change."""
    import sqlite3

    db = sqlite3.connect(root / "41526372" / "store.db")
    names = [n for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    rows = {n: sorted(map(repr, db.execute(f"SELECT * FROM {n}"))) for n in names}
    db.close()
    return rows


@pytest.mark.law("P12")
def test_emit_never_writes_a_job_into_a_dossier(tmp_path, capsys):
    """``kit emit --dossiers`` would insert a Job from a hand-written pack: no source stored,
    no answer recorded. It is refused, names the recorded paths and changes nothing."""
    import json

    from kit.store import open_dossier

    root = tmp_path / "dossiers"
    open_dossier(root, "41526372")
    before = _dossier_rows(root)
    (tmp_path / "pack.json").write_text(json.dumps(_emit_pack()))
    assert main(["emit", str(tmp_path / "pack.json"), "--dossiers", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "kit intake" in captured.err and "kit answer" in captured.err
    assert "Dispatcher" in captured.err
    assert _dossier_rows(root) == before
    assert not open_dossier(root, "41526372").jobs("2026-09")
    assert not (tmp_path / "fresh").exists()
    assert main(["emit", str(tmp_path / "pack.json"), "--dossiers", str(tmp_path / "fresh")]) == 1
    assert not (tmp_path / "fresh").exists()


def _decont(tmp_path) -> tuple:
    """A container pack and a decont_split answer naming one e-invoice part."""
    import hashlib
    import json

    part = hashlib.sha256(b"inv").hexdigest()
    container = _emit_pack(
        source_doc_id="decont_cheltuieli", kinds=["xlsx"], counterparty_cui=None, identity_ok=True
    )
    answer = {
        "parts": [
            {
                "part_hash": part,
                "source_doc_id": "ro_efactura_ubl",
                "kinds": ["ubl_spv"],
                "counterparty_cui": "73645193",
            }
        ]
    }
    (tmp_path / "container.json").write_text(json.dumps(container))
    (tmp_path / "answer.json").write_text(json.dumps(answer))
    return tmp_path / "container.json", tmp_path / "answer.json", part


@pytest.mark.law("P12")
def test_emit_split_with_dossiers_is_refused_not_ignored(tmp_path, capsys):
    from kit.store import open_dossier

    container, answer, _ = _decont(tmp_path)
    root = tmp_path / "dossiers"
    open_dossier(root, "41526372")
    before = _dossier_rows(root)
    args = ["emit", str(container), "--split", str(answer), "--dossiers", str(root)]
    assert main(args) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "kit answer" in captured.err and "Dispatcher" in captured.err
    assert _dossier_rows(root) == before


@pytest.mark.law("P12")
def test_a_split_child_cannot_become_a_job_through_emit(tmp_path, capsys):
    """The reviewer's chain: ``--split`` prints a child with identity_ok true, and emitting that
    child with ``--dossiers`` inserted a Job with no answer and no source. It now cannot."""
    import json

    from kit.store import open_dossier

    container, answer, part = _decont(tmp_path)
    assert main(["emit", str(container), "--split", str(answer)]) == 0
    children = json.loads(capsys.readouterr().out)
    assert children[0]["pack"]["identity_ok"] and children[0]["decision"]["emit"]
    assert not (tmp_path / "dossiers").exists()  # the dry run writes nothing
    (tmp_path / "child.json").write_text(json.dumps(children[0]["pack"]))
    root = tmp_path / "dossiers"
    assert main(["emit", str(tmp_path / "child.json"), "--dossiers", str(root)]) == 1
    assert "kit intake" in capsys.readouterr().err
    d = open_dossier(root, "41526372")
    assert not d.jobs("2026-09")
    assert d.answers(f"batch:{part}") == []


def test_emit_without_dossiers_prints_the_decision_unchanged(tmp_path, capsys):
    import json

    from kit.catalog import load_catalog
    from kit.sorting import Pack, decide

    pack = _emit_pack()
    (tmp_path / "pack.json").write_text(json.dumps(pack))
    assert main(["emit", str(tmp_path / "pack.json")]) == 0
    expected = decide(load_catalog(Path("catalog")), Pack.model_validate(pack)).model_dump()
    assert json.loads(capsys.readouterr().out) == expected


def test_answer_command(tmp_path, capsys):
    import json

    (tmp_path / "q.json").write_text(json.dumps({"job_id": "j1"}))
    (tmp_path / "ok.json").write_text(json.dumps({"decision": "approve"}))
    (tmp_path / "bad.json").write_text(json.dumps({"decision": "maybe"}))
    base = [
        "answer",
        "--dossiers",
        str(tmp_path / "d"),
        "--cui",
        "41526372",
        "--issue",
        "job:j1",
        "--kind",
        "v3_approve",
        "--question",
        str(tmp_path / "q.json"),
        "--operator",
        "Ana",
    ]
    assert main([*base, "--answer", str(tmp_path / "bad.json")]) == 3
    assert "decision" in json.loads(capsys.readouterr().out)["error"]
    assert main([*base, "--answer", str(tmp_path / "ok.json")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "accepted"
    assert main([*base, "--answer", str(tmp_path / "ok.json"), "--actor", "saga_agent"]) == 1
    assert "for a person" in capsys.readouterr().err


def test_route_command(tmp_path, capsys):
    import json

    (tmp_path / "f.json").write_text(json.dumps({"recon_open": True}))
    assert main(["route", "--procedure", "close", "--facts", str(tmp_path / "f.json")]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "recon"
    (tmp_path / "bad.json").write_text(json.dumps({"model_says": "file"}))
    assert main(["route", "--procedure", "close", "--facts", str(tmp_path / "bad.json")]) == 1
    assert "model_says" in capsys.readouterr().err
