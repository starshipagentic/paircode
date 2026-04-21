"""Tests for paircode.peerlab — per-peer parallel labs with own .git."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from paircode.cli import main
from paircode.handshake import ProposedPeer
from paircode.peerlab import (
    LAB_GITIGNORE_MARKER,
    PEERLAB_DIRNAME,
    ensure_gitignore,
    ensure_lab_gitignore,
    ensure_peer_labs,
    peer_lab_path,
)
from paircode.state import find_paircode, init_paircode


# ---------------------------------------------------------------------------
# ensure_peer_labs — scaffold + seed + git init + initial commit
# ---------------------------------------------------------------------------

def _seed_roster_with(tmp_path: Path, monkeypatch) -> None:
    """Make propose_roster return codex + gemini so ensure-scaffold populates
    peers.yaml with both, creating their sandbox dirs too."""
    peers = [
        ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes=""),
        ProposedPeer(id="peer-b-gemini", cli="gemini", priority="low", notes=""),
    ]
    monkeypatch.setattr("paircode.cli.propose_roster", lambda: peers)


def _init_and_scaffold(tmp_path: Path, monkeypatch) -> None:
    """Seed a .paircode/ + populated project root in tmp_path."""
    # Simulate a small existing project at tmp_path
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n")
    (tmp_path / "README.md").write_text("# demo\n")
    monkeypatch.chdir(tmp_path)
    _seed_roster_with(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])


def test_ensure_peer_labs_creates_dirs_and_seeds_and_inits_git(tmp_path, monkeypatch):
    """First run: each peer gets a lab, seeded from project root, with own
    .git/ and an initial commit."""
    _init_and_scaffold(tmp_path, monkeypatch)
    state = find_paircode()
    results = ensure_peer_labs(state)
    assert len(results) == 2
    statuses = {r.peer_id: r.status for r in results}
    assert statuses["peer-a-codex"] == "created"
    assert statuses["peer-b-gemini"] == "created"

    peerlab_root = tmp_path / PEERLAB_DIRNAME
    for pid in ("peer-a-codex", "peer-b-gemini"):
        lab = peerlab_root / pid
        assert lab.is_dir(), f"{lab} missing"
        # Seeded contents
        assert (lab / "src" / "app.py").is_file()
        assert (lab / "README.md").is_file()
        # Own git
        assert (lab / ".git").is_dir()
        # Initial commit exists — HEAD resolves
        r = subprocess.run(
            ["git", "-C", str(lab), "log", "-1", "--oneline"],
            capture_output=True, text=True, check=False,
        )
        assert r.returncode == 0
        assert r.stdout.strip(), f"no initial commit in {lab}"


def test_ensure_peer_labs_is_idempotent(tmp_path, monkeypatch):
    """Second call: labs already exist → status 'already-exists', no re-seed."""
    _init_and_scaffold(tmp_path, monkeypatch)
    state = find_paircode()
    ensure_peer_labs(state)

    # Simulate the peer evolving: write a new file, commit
    lab = peer_lab_path(state, "peer-a-codex")
    (lab / "new-work.py").write_text("# codex added this\n")
    subprocess.run(["git", "-C", str(lab), "add", "-A"], check=False)
    subprocess.run(
        ["git", "-C", str(lab), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--quiet", "-m", "codex evolution"],
        check=False,
    )

    # Re-run ensure — should NOT wipe codex's evolution
    results = ensure_peer_labs(state)
    statuses = {r.peer_id: r.status for r in results}
    assert statuses["peer-a-codex"] == "already-exists"
    assert statuses["peer-b-gemini"] == "already-exists"
    assert (lab / "new-work.py").exists(), "idempotent run wiped codex's work!"


def test_ensure_gitignore_adds_peerlab_line(tmp_path):
    """First call appends `.peerlab/` to .gitignore; second call no-ops."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("__pycache__/\n.venv/\n")
    assert ensure_gitignore(tmp_path) is True
    text = gitignore.read_text()
    assert ".peerlab/" in text
    assert "peerlab — per-peer" in text

    # Second call: already there → no change
    before = text
    assert ensure_gitignore(tmp_path) is False
    assert gitignore.read_text() == before


def test_ensure_gitignore_creates_file_if_missing(tmp_path):
    """No .gitignore → create it with the peerlab entry."""
    gitignore = tmp_path / ".gitignore"
    assert not gitignore.exists()
    assert ensure_gitignore(tmp_path) is True
    assert ".peerlab/" in gitignore.read_text()


def test_ensure_peer_labs_greenfield_minimal_seed(tmp_path, monkeypatch):
    """On a near-empty project, labs still get created with git. The only
    non-git content is the `.gitignore` that ensure_peer_labs itself added
    to the outer repo (then rsync copies it into each lab)."""
    monkeypatch.chdir(tmp_path)
    _seed_roster_with(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(main, ["ensure-scaffold"])
    state = find_paircode()
    results = ensure_peer_labs(state)
    statuses = {r.peer_id: r.status for r in results}
    assert statuses["peer-a-codex"] == "created"
    lab = peer_lab_path(state, "peer-a-codex")
    assert lab.is_dir()
    assert (lab / ".git").is_dir()
    children = sorted(p.name for p in lab.iterdir() if p.name != ".git")
    # Greenfield: only the inherited .gitignore, nothing else (no source files)
    assert children == [".gitignore"], f"expected just .gitignore, got {children}"


# ---------------------------------------------------------------------------
# CLI surface — paircode peerlab ensure / list
# ---------------------------------------------------------------------------

def test_paircode_peerlab_ensure_command(tmp_path, monkeypatch):
    _init_and_scaffold(tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(main, ["peerlab", "ensure"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".peerlab" / "peer-a-codex").is_dir()
    assert (tmp_path / ".peerlab" / "peer-b-gemini").is_dir()


def test_paircode_peerlab_list_shows_head(tmp_path, monkeypatch):
    _init_and_scaffold(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(main, ["peerlab", "ensure"])
    result = runner.invoke(main, ["peerlab", "list"])
    assert result.exit_code == 0
    assert "peer-a-codex" in result.output
    assert "peer-b-gemini" in result.output


def test_paircode_peerlab_help_is_reachable():
    runner = CliRunner()
    for argv in (["peerlab", "--help"], ["peerlab", "ensure", "--help"],
                 ["peerlab", "invoke", "--help"], ["peerlab", "list", "--help"]):
        result = runner.invoke(main, argv)
        assert result.exit_code == 0, f"{argv}: {result.output}"


# ---------------------------------------------------------------------------
# Seed excludes honored
# ---------------------------------------------------------------------------

def test_lab_gitignore_has_pycache_on_fresh_lab(tmp_path, monkeypatch):
    """Fresh lab's .gitignore excludes __pycache__ and bytecode so peer
    commits don't pull in build junk. Regression for v0.12.0 bug where
    `git add -A` in peer labs committed .pyc files."""
    _init_and_scaffold(tmp_path, monkeypatch)
    state = find_paircode()
    ensure_peer_labs(state)
    lab = peer_lab_path(state, "peer-a-codex")
    gitignore = lab / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert "__pycache__/" in content
    assert "*.py[cod]" in content
    assert LAB_GITIGNORE_MARKER in content


def test_ensure_lab_gitignore_appends_to_existing(tmp_path):
    """If user's project already has a .gitignore (rsync brought it over),
    the peerlab block is APPENDED — user rules preserved."""
    lab = tmp_path
    (lab / ".gitignore").write_text("# user project rules\nsecrets.env\n")
    assert ensure_lab_gitignore(lab) is True
    content = (lab / ".gitignore").read_text()
    assert "secrets.env" in content  # user rule preserved
    assert LAB_GITIGNORE_MARKER in content  # our block added


def test_ensure_lab_gitignore_is_idempotent(tmp_path):
    """Second call no-ops if marker already there."""
    lab = tmp_path
    assert ensure_lab_gitignore(lab) is True
    before = (lab / ".gitignore").read_text()
    assert ensure_lab_gitignore(lab) is False
    assert (lab / ".gitignore").read_text() == before


def test_initial_commit_authored_as_peer_id(tmp_path, monkeypatch):
    """Initial seed commit must be authored as the peer_id so replay
    (git log) attributes work to each peer. Fixes v0.12.0 where commits
    were authored as generic 'paircode-peerlab'."""
    _init_and_scaffold(tmp_path, monkeypatch)
    state = find_paircode()
    ensure_peer_labs(state)
    for pid in ("peer-a-codex", "peer-b-gemini"):
        lab = peer_lab_path(state, pid)
        r = subprocess.run(
            ["git", "-C", str(lab), "log", "-1", "--format=%an <%ae>"],
            capture_output=True, text=True, check=False,
        )
        assert pid in r.stdout, f"commit author should contain {pid}; got {r.stdout}"
        assert f"{pid}@peerlab.local" in r.stdout


def test_different_peers_produce_different_initial_commits(tmp_path, monkeypatch):
    """Distinct peer_ids as commit authors mean the seed commit SHAs differ
    across labs — proves independence beyond 'same content, same author,
    accidental SHA collision'."""
    _init_and_scaffold(tmp_path, monkeypatch)
    state = find_paircode()
    ensure_peer_labs(state)
    codex_lab = peer_lab_path(state, "peer-a-codex")
    gemini_lab = peer_lab_path(state, "peer-b-gemini")

    def head_sha(lab):
        r = subprocess.run(
            ["git", "-C", str(lab), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        return r.stdout.strip()

    assert head_sha(codex_lab) != head_sha(gemini_lab), (
        "initial seed commits should differ across labs since authors differ"
    )


def test_seed_excludes_dot_paircode_and_dot_git(tmp_path, monkeypatch):
    """Seeded labs must not contain `.paircode/` (recursion) or the outer
    repo's `.git/` (each lab gets its own fresh git instead)."""
    # Project has a real outer .git with real history
    subprocess.run(["git", "-C", str(tmp_path), "init", "--quiet"], check=False)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--quiet", "--allow-empty", "-m", "outer initial"],
        check=False,
    )
    # Populate via the shared helper (creates src/app.py + README.md)
    _init_and_scaffold(tmp_path, monkeypatch)
    state = find_paircode()
    ensure_peer_labs(state)
    lab = peer_lab_path(state, "peer-a-codex")
    # Lab must not have .paircode (recursion guard)
    assert not (lab / ".paircode").exists(), "lab should not contain .paircode/"
    # Lab's .git exists — its OWN
    assert (lab / ".git").exists()
    # Critically, the outer repo's .git log must NOT have leaked into the lab's
    # git log. They're independent histories.
    outer_log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    lab_log = subprocess.run(
        ["git", "-C", str(lab), "log", "--oneline"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert "outer initial" in outer_log
    assert "outer initial" not in lab_log, "outer git history leaked into lab!"


# ---------------------------------------------------------------------------
# Installer — /peerlab.md deployed alongside /paircode.md
# ---------------------------------------------------------------------------

def test_installer_deploys_peerlab_slash_command(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    import importlib

    import paircode.detect as d
    import paircode.installer as inst
    importlib.reload(d)
    importlib.reload(inst)

    monkeypatch.setattr("shutil.which", lambda b: f"/fake/{b}")

    from cliworker.core import CLIResult
    from cliworker.registry import CLISpec

    def fake_invoke(cli, *args, **kwargs):
        return CLIResult(
            spec=CLISpec(cli=cli), ok=True, stdout="", stderr="",
            duration_s=0.01, returncode=0, argv=[cli, *args], skipped_reason=None,
        )
    monkeypatch.setattr("paircode.installer.invoke", fake_invoke)

    inst.install_all()
    peerlab_cmd = fake_home / ".claude" / "commands" / "peerlab.md"
    assert peerlab_cmd.exists(), "install_claude must deploy /peerlab.md"
    assert "peerlab" in peerlab_cmd.read_text()
