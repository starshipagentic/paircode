"""Smoke tests for the CLI scaffold + install subsystem."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from paircode import __version__
from paircode.cli import main
from paircode.detect import CliInfo  # noqa: F401 — used by other tests in repo


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
        "ensure-scaffold",
        "focus",
        "roster",
        "invoke",
    ):
        assert subcmd in result.output


def test_bare_invocation_shows_welcome():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "paircode" in result.output


def test_install_writes_claude_and_invokes_native_register(tmp_path, monkeypatch):
    """v0.10: claude is file-drop, codex + gemini use native-register via
    cliworker.invoke(). Verify the right file lands AND the right subprocess
    commands get called."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    def fake_which(binary):
        return f"/fake/bin/{binary}"

    monkeypatch.setattr("shutil.which", fake_which)

    # Capture invoke() calls — codex + gemini installs go through it
    invoked: list[tuple] = []

    def fake_invoke(cli, *args, **kwargs):
        from cliworker.core import CLIResult
        from cliworker.registry import CLISpec

        invoked.append((cli, args))
        # For idempotency check calls (gemini extensions list): return empty stdout
        # so it's "not installed" and the real install runs.
        if args and args[0] == "extensions" and "list" in args:
            return CLIResult(
                spec=CLISpec(cli=cli), ok=True, stdout="", stderr="",
                duration_s=0.01, returncode=0, argv=[cli, *args], skipped_reason=None,
            )
        # For actual install calls, succeed.
        return CLIResult(
            spec=CLISpec(cli=cli), ok=True, stdout="installed", stderr="",
            duration_s=0.1, returncode=0, argv=[cli, *args], skipped_reason=None,
        )

    monkeypatch.setattr("paircode.installer.invoke", fake_invoke)

    results = inst.install_all()
    actions = {r.cli_name: r.action for r in results}

    assert actions["claude"] == "installed"
    assert actions["codex"] == "installed"
    assert actions["gemini"] == "installed"

    # Claude: file-drop landed on disk
    claude_cmd = fake_home / ".claude" / "commands" / "paircode.md"
    assert claude_cmd.exists()
    assert "paircode" in claude_cmd.read_text()

    # Codex: the invoke() call ran `codex marketplace add starshipagentic/paircode-codex`
    codex_calls = [c for c in invoked if c[0] == "codex"]
    assert any(
        c[1] == ("marketplace", "add", "starshipagentic/paircode-codex")
        for c in codex_calls
    ), f"Expected codex marketplace add call; got {codex_calls}"

    # Gemini: the invoke() call ran `gemini extensions install <url> --consent`
    gemini_install = [
        c for c in invoked
        if c[0] == "gemini" and "install" in c[1] and "--consent" in c[1]
    ]
    assert gemini_install, f"Expected gemini extensions install --consent; got {invoked}"

    # We do NOT write the legacy broken codex rules file
    assert not (fake_home / ".codex" / "rules" / "paircode.rules").exists()


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
