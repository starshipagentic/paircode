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
    # claude gets a real install (writes slash command file)
    assert actions["claude"] == "installed"
    # codex and gemini are intentional no-ops as of v0.8 — we stopped writing
    # broken files to ~/.codex/rules/. Both should report "noop" not "installed".
    assert actions["codex"] == "noop", (
        f"codex should be noop (not installed), got {actions['codex']!r}"
    )
    assert actions["gemini"] == "noop", (
        f"gemini should be noop (not installed), got {actions['gemini']!r}"
    )
    # Verify claude slash command actually landed on disk
    claude_cmd = fake_home / ".claude" / "commands" / "paircode.md"
    assert claude_cmd.exists()
    content = claude_cmd.read_text()
    assert "paircode" in content
    # And verify we do NOT write a broken codex rules file
    codex_rules = fake_home / ".codex" / "rules" / "paircode.rules"
    assert not codex_rules.exists(), (
        f"paircode should not write {codex_rules} — that file breaks codex's rule loader"
    )


def test_install_cleans_legacy_codex_rules_file(tmp_path, monkeypatch):
    """Users who installed paircode 0.1–0.7 have a broken ~/.codex/rules/paircode.rules.
    Running install again (or any time) must clean it up."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    # Seed the legacy broken file
    legacy = fake_home / ".codex" / "rules" / "paircode.rules"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# old broken markdown-in-starlark\n")
    assert legacy.exists()

    def fake_which(binary):
        return f"/fake/bin/{binary}"

    monkeypatch.setattr("shutil.which", fake_which)
    inst.install_all()

    # Legacy file should be gone after install_all
    assert not legacy.exists(), (
        "install_all must remove the legacy ~/.codex/rules/paircode.rules "
        "(it's Starlark-parsed and our markdown broke codex)"
    )
