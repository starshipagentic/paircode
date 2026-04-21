"""End-to-end CLI smoke tests for paircode (Arch B, v0.11+).

Invokes the real CLI via CliRunner and asserts on real output. Catches
regressions unit tests miss: broken subcommands, click routing drift,
wrong default behavior, missing help content.

Arch B surface: install / uninstall / ensure-scaffold / focus new / focus
active / roster / invoke / bare (state print).
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
        ["ensure-scaffold", "--help"],
        ["focus", "--help"],
        ["focus", "new", "--help"],
        ["focus", "active", "--help"],
        ["roster", "--help"],
        ["invoke", "--help"],
        ["converge", "--help"],
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
    for cmd in ("install", "uninstall", "ensure-scaffold",
                "focus", "roster", "invoke", "converge"):
        assert cmd in result.output, f"Main --help missing subcommand: {cmd}"


def test_retired_verbs_are_gone():
    """init/handshake/status/stage/seal/drive were removed in Arch B.
    If anyone reintroduces them as user-facing verbs, this breaks."""
    runner = CliRunner()
    help_text = runner.invoke(main, ["--help"]).output
    for retired in ("init", "handshake", "status", "stage", "seal", "drive"):
        # Check that retired verbs aren't listed in the commands section.
        # `invoke` legitimately contains the substring of none of these; safe.
        lines = [l for l in help_text.splitlines() if l.strip().startswith(retired)]
        assert not lines, (
            f"Retired verb {retired!r} surfaced in top-level help:\n{help_text}"
        )


def test_version_string_matches_dunder():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


# ---------------------------------------------------------------------------
# Bare paircode — state print, former `status`
# ---------------------------------------------------------------------------

def test_bare_paircode_without_state_prints_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "install" in result.output.lower()


def test_bare_paircode_finds_existing_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Seed via ensure-scaffold (replaces old init)
    runner = CliRunner()
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert ".paircode" in result.output


# ---------------------------------------------------------------------------
# ensure-scaffold
# ---------------------------------------------------------------------------

def test_ensure_scaffold_creates_paircode_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    result = runner.invoke(main, ["ensure-scaffold"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".paircode").exists()
    assert (tmp_path / ".paircode" / "JOURNEY.md").exists()
    assert (tmp_path / ".paircode" / "peers.yaml").exists()


def test_ensure_scaffold_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    second = runner.invoke(main, ["ensure-scaffold"])
    assert second.exit_code == 0, second.output
    # Silent on second run (no init, no handshake — roster is still empty).
    assert second.output.strip() == ""


# ---------------------------------------------------------------------------
# focus new / focus active
# ---------------------------------------------------------------------------

def test_focus_new_creates_dir_and_prints_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["focus", "new", "my-first-focus", "--prompt", "hello"])
    assert result.exit_code == 0, result.output
    focus_path = Path(result.output.strip())
    assert focus_path.exists()
    assert focus_path.name.startswith("focus-01-")
    assert (focus_path / "FOCUS.md").exists()
    assert (focus_path / "research").exists()


def test_focus_active_without_focus_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["focus", "active"])
    assert result.exit_code != 0
    assert "no focus" in result.output.lower()


def test_focus_active_prints_most_recent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    runner.invoke(main, ["focus", "new", "one"])
    runner.invoke(main, ["focus", "new", "two"])
    result = runner.invoke(main, ["focus", "active"])
    assert result.exit_code == 0, result.output
    # "two" was created last → it's active (sort by focus-NN prefix)
    assert "focus-02-two" in result.output


# ---------------------------------------------------------------------------
# roster
# ---------------------------------------------------------------------------

def test_roster_empty_when_no_peers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["roster"])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_roster_prints_peer_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from paircode.handshake import ProposedPeer
    peers = [
        ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes=""),
        ProposedPeer(id="peer-b-gemini", cli="gemini", priority="low", notes=""),
    ]
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: peers)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["roster"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert "peer-a-codex" in lines
    assert "peer-b-gemini" in lines


def test_roster_alpha_excludes_matching_cli(tmp_path, monkeypatch):
    """`roster --alpha codex` excludes codex-cli peers unless they're the only option."""
    monkeypatch.chdir(tmp_path)
    from paircode.handshake import ProposedPeer
    peers = [
        ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes=""),
        ProposedPeer(id="peer-b-gemini", cli="gemini", priority="low", notes=""),
    ]
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: peers)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["roster", "--alpha", "codex"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert "peer-a-codex" not in lines
    assert "peer-b-gemini" in lines


def test_roster_missing_peer_falls_back_silently(tmp_path, monkeypatch):
    """`--peer gemini` when gemini isn't in the roster falls back to all peers,
    never errors."""
    monkeypatch.chdir(tmp_path)
    from paircode.handshake import ProposedPeer
    peers = [
        ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes=""),
    ]
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: peers)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["roster", "--peer", "peer-z-gemini"])
    assert result.exit_code == 0, result.output
    # Silent fallback — codex shows up because it's all we've got
    lines = result.output.strip().splitlines()
    assert "peer-a-codex" in lines


def test_roster_last_resort_includes_alpha_when_nothing_else(tmp_path, monkeypatch):
    """If --alpha claude is set but only claude is in the roster, claude still
    gets included — last-resort rule."""
    monkeypatch.chdir(tmp_path)
    from paircode.handshake import ProposedPeer
    # Stub out propose_roster so the re-detection step finds nothing new
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    # Seed a claude-only roster manually
    from paircode.state import find_paircode, write_peers
    state = find_paircode()
    write_peers(state, [{"id": "peer-a-claude", "cli": "claude", "priority": "low"}])

    result = runner.invoke(main, ["roster", "--alpha", "claude"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert "peer-a-claude" in lines, (
        "Claude should be last-resort peer when nothing else is available"
    )


# ---------------------------------------------------------------------------
# invoke — the team-lead's peer-firing helper
# ---------------------------------------------------------------------------

def test_invoke_unknown_peer_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(
        main,
        ["invoke", "peer-z-nonexistent", "hi", "--out", str(tmp_path / "out.md")],
    )
    assert result.exit_code != 0
    assert "unknown peer" in result.output.lower()


def test_invoke_calls_run_peer_and_writes_trace(tmp_path, monkeypatch):
    """invoke must delegate to runner.run_peer with the peer's cli + model
    from peers.yaml, and the --out path lands on disk (run_peer handles the
    write; here we just confirm the wiring)."""
    from paircode.handshake import ProposedPeer
    from paircode.runner import PeerRunResult

    monkeypatch.chdir(tmp_path)
    peers = [ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes="")]
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: peers)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])

    captured = {}

    def fake_run_peer(peer_id, cli, prompt, output_path, **kwargs):
        captured["peer_id"] = peer_id
        captured["cli"] = cli
        captured["prompt"] = prompt
        captured["output_path"] = output_path
        captured["fast"] = kwargs.get("fast")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("fake peer output", encoding="utf-8")
        return PeerRunResult(
            peer_id=peer_id, cli=cli, ok=True, stdout="fake", stderr="",
            duration_s=0.1, command=[],
        )

    monkeypatch.setattr("paircode.cli.run_peer", fake_run_peer)

    out_file = tmp_path / "peer-a-v1.md"
    result = runner.invoke(main, [
        "invoke", "peer-a-codex", "what is TCP?",
        "--out", str(out_file),
    ])
    assert result.exit_code == 0, result.output
    assert captured["peer_id"] == "peer-a-codex"
    assert captured["cli"] == "codex"
    assert captured["prompt"] == "what is TCP?"
    assert captured["output_path"] == out_file
    assert out_file.exists()


def test_converge_copies_latest_vn_to_final(tmp_path, monkeypatch):
    """`paircode converge <stage>` copies each peer's (and alpha's) latest vN
    to {id}-FINAL.md. Mechanical replacement for the template's bash loop."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    focus_out = runner.invoke(main, ["focus", "new", "testfocus"])
    focus_dir = Path(focus_out.output.strip())

    research = focus_dir / "research"
    (research / "alpha-v1.md").write_text("alpha round 1", encoding="utf-8")
    (research / "alpha-v2.md").write_text("alpha round 2", encoding="utf-8")
    (research / "peer-a-codex-v1.md").write_text("codex round 1", encoding="utf-8")

    result = runner.invoke(main, ["converge", "research"])
    assert result.exit_code == 0, result.output

    assert (research / "alpha-FINAL.md").exists()
    assert (research / "peer-a-codex-FINAL.md").exists()
    # FINAL pulls the highest vN for alpha
    assert (research / "alpha-FINAL.md").read_text() == "alpha round 2"


def test_converge_without_focus_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: [])
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    result = runner.invoke(main, ["converge", "research"])
    assert result.exit_code != 0
    assert "focus" in result.output.lower()


def test_invoke_failure_exits_nonzero(tmp_path, monkeypatch):
    from paircode.handshake import ProposedPeer
    from paircode.runner import PeerRunResult

    monkeypatch.chdir(tmp_path)
    peers = [ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes="")]
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: peers)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])

    def failing(peer_id, cli, prompt, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("FAIL trace", encoding="utf-8")
        return PeerRunResult(
            peer_id=peer_id, cli=cli, ok=False, stdout="",
            stderr="subscription lapsed", duration_s=1.0, command=[],
        )

    monkeypatch.setattr("paircode.cli.run_peer", failing)

    result = runner.invoke(main, [
        "invoke", "peer-a-codex", "hi",
        "--out", str(tmp_path / "out.md"),
    ])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Runner <-> cliworker integration (kept from v0.10)
# ---------------------------------------------------------------------------

def test_runner_imports_cliworker():
    """Regression: paircode.runner must import and delegate to cliworker as
    of v0.8+. If someone reverts the refactor, this test breaks."""
    import paircode.runner as runner_mod

    source = Path(runner_mod.__file__).read_text()
    assert "from cliworker" in source, (
        "paircode.runner must use cliworker — "
        "the whole point of v0.8 was to delegate to it"
    )
    assert "cliworker.run" in source or "import run" in source


def test_run_peer_wraps_cliworker_result(monkeypatch, tmp_path):
    """run_peer should call cliworker.run() and return a PeerRunResult
    with the peer_id set + the file-trace written to disk."""
    from paircode.runner import run_peer, PeerRunResult

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

    assert isinstance(result, PeerRunResult)
    assert result.peer_id == "peer-a-fake"
    assert result.cli == "claude"
    assert result.ok is True
    assert result.stdout == "mocked answer"
    assert result.duration_s == pytest.approx(0.42)

    assert out_path.exists()
    content = out_path.read_text()
    assert "peer_id: peer-a-fake" in content
    assert "cli: claude" in content
    assert "ok: True" in content
    assert "mocked answer" in content


def test_run_peer_with_failure_still_writes_trace(monkeypatch, tmp_path):
    """Failed peer runs must still leave a file-trace on disk."""
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
    from cliworker.core import CLIResult
    from cliworker.registry import CLISpec

    def fake(cli, *args, **kwargs):
        captured.append((cli, args))
        return CLIResult(
            spec=CLISpec(cli=cli), ok=True, stdout="", stderr="",
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

    assert not (fake_home / ".codex" / "rules" / "paircode.rules").exists()


def test_installer_claude_writes_slash_command(tmp_path, monkeypatch):
    """install_claude drops the /paircode slash command. Simple-path template
    uses stock Agent tool subagents — no custom sub-agent definition needed."""
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
    assert actions["claude"] == "installed"

    slash_cmd = fake_home / ".claude" / "commands" / "paircode.md"
    assert slash_cmd.exists(), "Slash command missing"
    assert "paircode roster" in slash_cmd.read_text(), (
        "Template should reference `paircode roster` — core helper used by team lead"
    )


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

    codex_add_calls = [c for c in captured if c[0] == "codex" and "marketplace" in c[1]]
    assert not codex_add_calls, f"should not re-invoke marketplace add; got {codex_add_calls}"


def test_installer_fails_gracefully_with_actionable_message(tmp_path, monkeypatch):
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
