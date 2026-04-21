"""Tests for paircode.peerlab — per-peer parallel labs with own .git.

peerlab maintains its own state under `.peerlab/`, fully independent of
`.paircode/`. Tests reflect that: no `paircode ensure-scaffold` in the
setup path.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from paircode.cli import main
from paircode.handshake import ProposedPeer
from paircode.peerlab import (
    LAB_GITIGNORE_MARKER,
    PEERLAB_DIRNAME,
    PEERLAB_PEERS_FILE,
    ensure_gitignore,
    ensure_lab_gitignore,
    ensure_peer_labs,
    find_peerlab,
    init_peerlab,
    peer_lab_path,
    read_peerlab_peers,
    write_peerlab_peers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_roster(monkeypatch) -> list[ProposedPeer]:
    """Fake handshake detection so init_peerlab writes a predictable roster."""
    peers = [
        ProposedPeer(id="peer-a-codex", cli="codex", priority="high", notes=""),
        ProposedPeer(id="peer-b-gemini", cli="gemini", priority="low", notes=""),
    ]
    monkeypatch.setattr("paircode.peerlab.propose_roster", lambda: peers, raising=False)
    # The import inside init_peerlab is lazy; patch at both sides to be safe
    monkeypatch.setattr("paircode.handshake.propose_roster", lambda: peers)
    return peers


def _setup_populated_project(tmp_path: Path, monkeypatch) -> None:
    """Simulate a small existing project at tmp_path, cd in, seed handshake."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n")
    (tmp_path / "README.md").write_text("# demo\n")
    monkeypatch.chdir(tmp_path)
    _seed_roster(monkeypatch)


# ---------------------------------------------------------------------------
# peerlab state independence — no .paircode/ touched
# ---------------------------------------------------------------------------

def test_init_peerlab_creates_dir_and_peers_yaml(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    assert state.root == tmp_path / PEERLAB_DIRNAME
    assert state.root.is_dir()
    assert state.peers_path == state.root / PEERLAB_PEERS_FILE
    assert state.peers_path.is_file()
    data = yaml.safe_load(state.peers_path.read_text()) or {}
    ids = [p["id"] for p in data.get("peers") or []]
    assert "peer-a-codex" in ids
    assert "peer-b-gemini" in ids


def test_peerlab_ensure_does_not_create_dot_paircode(tmp_path, monkeypatch):
    """Regression: /peerlab must NOT create .paircode/ as a side effect."""
    _setup_populated_project(tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(main, ["peerlab", "ensure"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".peerlab").is_dir()
    assert not (tmp_path / ".paircode").exists(), (
        "peerlab ensure must not touch .paircode/ — they're independent state dirs"
    )


def test_find_peerlab_walks_up(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    init_peerlab()
    # cd into a subdir; find_peerlab should still find .peerlab/ at root
    sub = tmp_path / "src"
    monkeypatch.chdir(sub)
    state = find_peerlab()
    assert state is not None
    assert state.root == tmp_path / PEERLAB_DIRNAME


def test_init_peerlab_is_idempotent(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state1 = init_peerlab()
    before = state1.peers_path.read_text()
    state2 = init_peerlab()
    assert state2.peers_path.read_text() == before  # no-op second call


# ---------------------------------------------------------------------------
# ensure_peer_labs — seed + git init + peer-authored commit
# ---------------------------------------------------------------------------

def test_ensure_peer_labs_creates_dirs_and_seeds_and_inits_git(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    results = ensure_peer_labs(state)
    statuses = {r.peer_id: r.status for r in results}
    assert statuses["peer-a-codex"] == "created"
    assert statuses["peer-b-gemini"] == "created"

    for pid in ("peer-a-codex", "peer-b-gemini"):
        lab = tmp_path / PEERLAB_DIRNAME / pid
        assert lab.is_dir()
        assert (lab / "src" / "app.py").is_file()
        assert (lab / "README.md").is_file()
        assert (lab / ".git").is_dir()
        r = subprocess.run(
            ["git", "-C", str(lab), "log", "-1", "--oneline"],
            capture_output=True, text=True, check=False,
        )
        assert r.stdout.strip(), f"no initial commit in {lab}"


def test_ensure_peer_labs_is_idempotent(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    ensure_peer_labs(state)
    lab = peer_lab_path(state, "peer-a-codex")
    (lab / "new-work.py").write_text("# codex added this\n")
    subprocess.run(["git", "-C", str(lab), "add", "-A"], check=False)
    subprocess.run(
        ["git", "-C", str(lab), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--quiet", "-m", "codex evolution"],
        check=False,
    )
    results = ensure_peer_labs(state)
    statuses = {r.peer_id: r.status for r in results}
    assert statuses["peer-a-codex"] == "already-exists"
    assert (lab / "new-work.py").exists()


def test_initial_commit_authored_as_peer_id(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    ensure_peer_labs(state)
    for pid in ("peer-a-codex", "peer-b-gemini"):
        lab = peer_lab_path(state, pid)
        r = subprocess.run(
            ["git", "-C", str(lab), "log", "-1", "--format=%an <%ae>"],
            capture_output=True, text=True, check=False,
        )
        assert pid in r.stdout
        assert f"{pid}@peerlab.local" in r.stdout


def test_different_peers_produce_different_initial_commits(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    ensure_peer_labs(state)
    codex_lab = peer_lab_path(state, "peer-a-codex")
    gemini_lab = peer_lab_path(state, "peer-b-gemini")

    def head_sha(lab):
        r = subprocess.run(
            ["git", "-C", str(lab), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        return r.stdout.strip()

    assert head_sha(codex_lab) != head_sha(gemini_lab)


# ---------------------------------------------------------------------------
# lab .gitignore — python/editor defaults
# ---------------------------------------------------------------------------

def test_lab_gitignore_has_pycache_on_fresh_lab(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    ensure_peer_labs(state)
    lab = peer_lab_path(state, "peer-a-codex")
    content = (lab / ".gitignore").read_text()
    assert "__pycache__/" in content
    assert "*.py[cod]" in content
    assert LAB_GITIGNORE_MARKER in content


def test_ensure_lab_gitignore_appends_to_existing(tmp_path):
    (tmp_path / ".gitignore").write_text("# user project rules\nsecrets.env\n")
    assert ensure_lab_gitignore(tmp_path) is True
    content = (tmp_path / ".gitignore").read_text()
    assert "secrets.env" in content
    assert LAB_GITIGNORE_MARKER in content


def test_ensure_lab_gitignore_is_idempotent(tmp_path):
    assert ensure_lab_gitignore(tmp_path) is True
    before = (tmp_path / ".gitignore").read_text()
    assert ensure_lab_gitignore(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text() == before


# ---------------------------------------------------------------------------
# Outer .gitignore — appends .peerlab/
# ---------------------------------------------------------------------------

def test_ensure_gitignore_adds_peerlab_line(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("__pycache__/\n.venv/\n")
    assert ensure_gitignore(tmp_path) is True
    text = gitignore.read_text()
    assert ".peerlab/" in text
    assert "peerlab — per-peer" in text
    assert ensure_gitignore(tmp_path) is False


# ---------------------------------------------------------------------------
# Seed excludes honored
# ---------------------------------------------------------------------------

def test_seed_excludes_dot_peerlab_and_outer_git_history(tmp_path, monkeypatch):
    subprocess.run(["git", "-C", str(tmp_path), "init", "--quiet"], check=False)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--quiet", "--allow-empty", "-m", "outer initial"],
        check=False,
    )
    _setup_populated_project(tmp_path, monkeypatch)
    state = init_peerlab()
    ensure_peer_labs(state)
    lab = peer_lab_path(state, "peer-a-codex")
    assert not (lab / ".peerlab").exists()
    assert not (lab / ".paircode").exists()
    assert (lab / ".git").exists()
    outer_log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    lab_log = subprocess.run(
        ["git", "-C", str(lab), "log", "--oneline"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert "outer initial" in outer_log
    assert "outer initial" not in lab_log


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_paircode_peerlab_help_is_reachable():
    runner = CliRunner()
    for argv in (["peerlab", "--help"], ["peerlab", "ensure", "--help"],
                 ["peerlab", "invoke", "--help"], ["peerlab", "list", "--help"],
                 ["peerlab", "roster", "--help"]):
        result = runner.invoke(main, argv)
        assert result.exit_code == 0, f"{argv}: {result.output}"


def test_paircode_peerlab_ensure_command(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(main, ["peerlab", "ensure"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".peerlab" / "peers.yaml").is_file()
    assert (tmp_path / ".peerlab" / "peer-a-codex").is_dir()
    assert (tmp_path / ".peerlab" / "peer-b-gemini").is_dir()
    # AND .paircode/ is NOT created
    assert not (tmp_path / ".paircode").exists()


def test_paircode_peerlab_list_shows_head(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(main, ["peerlab", "ensure"])
    result = runner.invoke(main, ["peerlab", "list"])
    assert result.exit_code == 0
    assert "peer-a-codex" in result.output
    assert "peer-b-gemini" in result.output


def test_paircode_peerlab_roster_prints_ids(tmp_path, monkeypatch):
    _setup_populated_project(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(main, ["peerlab", "ensure"])
    result = runner.invoke(main, ["peerlab", "roster"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "peer-a-codex" in lines
    assert "peer-b-gemini" in lines


def test_paircode_peerlab_roster_alpha_filter(tmp_path, monkeypatch):
    """roster --alpha codex drops codex-cli peers when others are available."""
    _setup_populated_project(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(main, ["peerlab", "ensure"])
    result = runner.invoke(main, ["peerlab", "roster", "--alpha", "codex"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "peer-a-codex" not in lines
    assert "peer-b-gemini" in lines


# ---------------------------------------------------------------------------
# Installer — /peerlab.md still deployed alongside /paircode.md
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
    assert peerlab_cmd.exists()
    assert "peerlab" in peerlab_cmd.read_text()
