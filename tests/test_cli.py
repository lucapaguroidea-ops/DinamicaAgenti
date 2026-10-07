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


def test_emit_into_a_dossier(tmp_path, capsys):
    import hashlib
    import json

    pack = {
        "client_cui": "41526372",
        "period": "2026-09",
        "source_hash": hashlib.sha256(b"doc").hexdigest(),
        "source_doc_id": "ro_efactura_ubl",
        "kinds": ["ubl_spv"],
        "our_role": "inbound",
        "counterparty_cui": "73645193",
    }
    (tmp_path / "pack.json").write_text(json.dumps(pack))
    args = ["emit", str(tmp_path / "pack.json"), "--dossiers", str(tmp_path / "dossiers")]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(args) == 0
    again = json.loads(capsys.readouterr().out)
    assert first["created"] and not again["created"] and first["job_id"] == again["job_id"]
    assert (tmp_path / "dossiers" / "41526372" / "store.db").is_file()
