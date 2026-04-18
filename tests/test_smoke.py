"""Smoke tests for the CLI scaffold + install subsystem."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from paircode import __version__
from paircode.cli import main
from paircode.detect import CliInfo, KNOWN_CLIS


def test_version_flag_prints_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_flag_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for subcmd in (
        "install",
        "uninstall",
        "handshake",
        "status",
        "init",
        "focus",
        "stage",
        "drive",
    ):
        assert subcmd in result.output


def test_bare_invocation_shows_welcome():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "paircode" in result.output


def test_handshake_shows_table(tmp_path, monkeypatch):
    # detect_all reads from KNOWN_CLIS; we rely on real PATH here for smoke test.
    runner = CliRunner()
    result = runner.invoke(main, ["handshake"])
    assert result.exit_code == 0
    # Table header should appear
    assert "CLI" in result.output
    # At minimum the known names should be listed
    for name in KNOWN_CLIS:
        assert name in result.output


def test_install_writes_to_tmp_claude(tmp_path, monkeypatch):
    """Redirect ~/.claude to a tmp dir and verify install writes the slash command."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    # Re-import so Path.home() resolves to the new HOME
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    # Force all three CLIs "installed" by monkeypatching shutil.which
    def fake_which(binary):
        return f"/fake/bin/{binary}"

    monkeypatch.setattr("shutil.which", fake_which)

    results = inst.install_all()
    actions = {r.cli_name: r.action for r in results}
    assert actions["claude"] == "installed"
    # Verify file landed
    claude_cmd = fake_home / ".claude" / "commands" / "paircode.md"
    assert claude_cmd.exists()
    content = claude_cmd.read_text()
    assert "paircode" in content
