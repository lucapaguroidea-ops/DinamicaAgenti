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
