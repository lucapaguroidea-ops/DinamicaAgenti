"""The CLI: built commands work, planned ones refuse instead of pretending."""

from kit.cli import PLANNED, main


def test_cui_command(capsys):
    assert main(["cui", "RO41526372"]) == 0
    assert "41526372 valid" in capsys.readouterr().out
    assert main(["cui", "41526371"]) == 1


def test_planned_commands_refuse(capsys):
    for name in PLANNED:
        assert main([name]) == 2
    assert "not built yet" in capsys.readouterr().err


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
