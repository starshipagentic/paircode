"""End-to-end CLI smoke tests for paircode (v0.8+).

Invokes the real CLI via CliRunner and asserts on real output. Catches
regressions unit tests miss: broken subcommands, click routing drift,
wrong default behavior, missing help content.

Mirrors the same approach we added to cliworker in its v0.5.5.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from paircode import __version__
from paircode.cli import main


# ---------------------------------------------------------------------------
# Help-lint: every registered command + every --help variant must work.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cmd_argv",
    [
        ["--help"],
        ["--version"],
        ["install", "--help"],
        ["uninstall", "--help"],
        ["handshake", "--help"],
        ["status", "--help"],
        ["init", "--help"],
        ["focus", "--help"],
        ["stage", "--help"],
        ["seal", "--help"],
        ["drive", "--help"],
    ],
)
def test_every_command_help_is_reachable(cmd_argv):
    runner = CliRunner()
    result = runner.invoke(main, cmd_argv)
    assert result.exit_code == 0, (
        f"{cmd_argv} exited {result.exit_code}:\n{result.output}"
    )
    assert result.output.strip(), f"{cmd_argv} printed nothing"


def test_main_help_lists_all_public_subcommands():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in (
        "install", "uninstall", "handshake", "status",
        "init", "focus", "stage", "seal", "drive",
    ):
        assert cmd in result.output, f"Main --help missing subcommand: {cmd}"


def test_version_string_matches_dunder():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


# ---------------------------------------------------------------------------
# Runner <-> cliworker integration
# ---------------------------------------------------------------------------

def test_runner_imports_cliworker():
    """Regression: paircode.runner must import and delegate to cliworker as
    of v0.8+. If someone reverts the refactor, this test breaks."""
    import paircode.runner as runner
    import cliworker

    # The run_peer function should internally call cliworker.run
    source = Path(runner.__file__).read_text()
    assert "from cliworker" in source, (
        "paircode.runner must use cliworker — "
        "the whole point of v0.8 was to delegate to it"
    )
    assert "cliworker.run" in source or "import run" in source


def test_run_peer_wraps_cliworker_result(monkeypatch, tmp_path):
    """run_peer should call cliworker.run() and return a PeerRunResult
    with the peer_id set + the file-trace written to disk."""
    from paircode.runner import run_peer, PeerRunResult

    # Intercept cliworker.run so no real subprocess fires
    from cliworker.core import CLIResult
    from cliworker import get_spec

    def fake_run(prompt, *specs, **kwargs):
        spec = specs[0] if specs else get_spec("claude")
        return [CLIResult(
            spec=spec, ok=True, stdout="mocked answer",
            stderr="", duration_s=0.42, returncode=0,
            argv=["fake", "claude", "-p", prompt], skipped_reason=None,
        )]

    monkeypatch.setattr("paircode.runner.run", fake_run)

    out_path = tmp_path / "peer-a-v1.md"
    result = run_peer(
        peer_id="peer-a-fake",
        cli="claude",
        prompt="what is TCP?",
        output_path=out_path,
        timeout_s=30,
    )

    # Returns a proper PeerRunResult
    assert isinstance(result, PeerRunResult)
    assert result.peer_id == "peer-a-fake"
    assert result.cli == "claude"
    assert result.ok is True
    assert result.stdout == "mocked answer"
    assert result.duration_s == pytest.approx(0.42)

    # File-trace landed with the correct header
    assert out_path.exists()
    content = out_path.read_text()
    assert "peer_id: peer-a-fake" in content
    assert "cli: claude" in content
    assert "ok: True" in content
    assert "mocked answer" in content


def test_run_peer_with_failure_still_writes_trace(monkeypatch, tmp_path):
    """Failed peer runs must still leave a file-trace on disk, with the
    failure captured — that's the whole point of 'every thought on disk'."""
    from paircode.runner import run_peer
    from cliworker.core import CLIResult
    from cliworker import get_spec

    def fake_run(prompt, *specs, **kwargs):
        spec = specs[0] if specs else get_spec("claude")
        return [CLIResult(
            spec=spec, ok=False, stdout="",
            stderr="subscription lapsed",
            duration_s=1.5, returncode=1, argv=[], skipped_reason=None,
        )]

    monkeypatch.setattr("paircode.runner.run", fake_run)

    out_path = tmp_path / "peer-v1.md"
    result = run_peer(
        peer_id="peer-x", cli="claude", prompt="hi",
        output_path=out_path,
    )
    assert result.ok is False
    assert out_path.exists()
    content = out_path.read_text()
    assert "FAILED" in content
    assert "subscription lapsed" in content


def test_run_peer_fast_kwarg_passes_through(monkeypatch, tmp_path):
    """run_peer(fast=True) must land as fast=True on cliworker.run()."""
    from paircode.runner import run_peer
    from cliworker.core import CLIResult
    from cliworker import get_spec

    captured = {}

    def fake_run(prompt, *specs, **kwargs):
        captured["fast"] = kwargs.get("fast")
        return [CLIResult(
            spec=specs[0], ok=True, stdout="ok", stderr="",
            duration_s=0.1, returncode=0, argv=[], skipped_reason=None,
        )]

    monkeypatch.setattr("paircode.runner.run", fake_run)

    run_peer(
        peer_id="p", cli="claude", prompt="hi",
        output_path=tmp_path / "x.md",
        fast=True,
    )
    assert captured["fast"] is True

    # And default: no fast
    captured.clear()
    run_peer(
        peer_id="p", cli="claude", prompt="hi",
        output_path=tmp_path / "y.md",
    )
    assert captured.get("fast") in (None, False)


# ---------------------------------------------------------------------------
# Installer: native-register for codex + gemini via cliworker.invoke()
# ---------------------------------------------------------------------------

def _fake_cliworker_invoke_success(captured):
    """Return a fake invoke that captures calls and always succeeds."""
    from cliworker.core import CLIResult
    from cliworker.registry import CLISpec

    def fake(cli, *args, **kwargs):
        captured.append((cli, args))
        stdout = ""
        # Simulate empty list output for gemini extensions list (idempotency check)
        return CLIResult(
            spec=CLISpec(cli=cli), ok=True, stdout=stdout, stderr="",
            duration_s=0.01, returncode=0, argv=[cli, *args], skipped_reason=None,
        )

    return fake


def test_installer_codex_calls_marketplace_add_via_invoke(tmp_path, monkeypatch):
    """paircode v0.10 delegates codex install to cliworker.invoke()
    running `codex marketplace add starshipagentic/paircode-codex`."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    monkeypatch.setattr("shutil.which", lambda b: f"/fake/{b}")
    captured: list[tuple] = []
    monkeypatch.setattr("paircode.installer.invoke", _fake_cliworker_invoke_success(captured))

    results = inst.install_all()
    actions = {r.cli_name: r.action for r in results}
    assert actions["codex"] == "installed"

    codex_calls = [c for c in captured if c[0] == "codex"]
    assert any(
        c[1] == ("marketplace", "add", "starshipagentic/paircode-codex")
        for c in codex_calls
    ), f"expected `codex marketplace add starshipagentic/paircode-codex`, got {codex_calls}"

    # Never writes the broken legacy rules file
    assert not (fake_home / ".codex" / "rules" / "paircode.rules").exists()


def test_installer_gemini_calls_extensions_install_via_invoke(tmp_path, monkeypatch):
    """paircode v0.10 runs `gemini extensions install <url> --consent`."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    monkeypatch.setattr("shutil.which", lambda b: f"/fake/{b}")
    captured: list[tuple] = []
    monkeypatch.setattr("paircode.installer.invoke", _fake_cliworker_invoke_success(captured))

    results = inst.install_all()
    actions = {r.cli_name: r.action for r in results}
    assert actions["gemini"] == "installed"

    gemini_installs = [
        c for c in captured
        if c[0] == "gemini" and c[1][0:2] == ("extensions", "install") and "--consent" in c[1]
    ]
    assert gemini_installs, f"expected gemini extensions install --consent; got {captured}"


def test_installer_codex_idempotent_when_already_registered(tmp_path, monkeypatch):
    """If the codex marketplace is already registered, install returns 'already'
    without re-invoking `codex marketplace add`."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex" / "config.toml").write_text(
        '[marketplaces.paircode]\nsource = "https://github.com/starshipagentic/paircode-codex.git"\n'
    )
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    monkeypatch.setattr("shutil.which", lambda b: f"/fake/{b}")
    captured: list[tuple] = []
    monkeypatch.setattr("paircode.installer.invoke", _fake_cliworker_invoke_success(captured))

    results = inst.install_all()
    codex_result = next(r for r in results if r.cli_name == "codex")
    assert codex_result.action == "already", (
        f"expected action='already'; got {codex_result.action!r} — {codex_result.message}"
    )

    # Marketplace-add must NOT have been invoked on codex
    codex_add_calls = [c for c in captured if c[0] == "codex" and "marketplace" in c[1]]
    assert not codex_add_calls, f"should not re-invoke marketplace add; got {codex_add_calls}"


def test_installer_fails_gracefully_with_actionable_message(tmp_path, monkeypatch):
    """When invoke() returns .ok=False, installer surfaces the command to run
    manually (copy-paste friendly)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst

    importlib.reload(d)
    importlib.reload(inst)

    monkeypatch.setattr("shutil.which", lambda b: f"/fake/{b}")

    def failing_invoke(cli, *args, **kwargs):
        from cliworker.core import CLIResult
        from cliworker.registry import CLISpec

        return CLIResult(
            spec=CLISpec(cli=cli), ok=False, stdout="", stderr="simulated failure",
            duration_s=0.01, returncode=1, argv=[cli, *args], skipped_reason=None,
        )

    monkeypatch.setattr("paircode.installer.invoke", failing_invoke)

    results = inst.install_all()

    codex_r = next(r for r in results if r.cli_name == "codex")
    assert codex_r.action == "failed"
    assert "codex marketplace add starshipagentic/paircode-codex" in codex_r.message

    gemini_r = next(r for r in results if r.cli_name == "gemini")
    assert gemini_r.action == "failed"
    assert "gemini extensions install" in gemini_r.message
    assert "--consent" in gemini_r.message


# ---------------------------------------------------------------------------
# Init + status dispatch smoke
# ---------------------------------------------------------------------------

def test_init_creates_paircode_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".paircode").exists()
    assert (tmp_path / ".paircode" / "JOURNEY.md").exists()
    assert (tmp_path / ".paircode" / "peers.yaml").exists()


def test_status_finds_paircode_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    # First init
    runner.invoke(main, ["init"])
    # Then status should find it and exit cleanly
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert ".paircode" in result.output


def test_status_without_paircode_dir_prints_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    # Should not crash; should suggest init
    assert result.exit_code == 0
    assert "init" in result.output.lower()
