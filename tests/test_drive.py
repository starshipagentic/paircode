"""Tests for handshake + drive.

Uses monkeypatched subprocess so no actual LLM calls happen during tests.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from paircode.drive import drive_research
from paircode.handshake import propose_roster
from paircode.state import init_paircode, write_peers


def test_propose_roster_returns_installed_peers_only(monkeypatch):
    # Force: claude + codex present, gemini missing, ollama missing
    import paircode.detect as d

    installed = {"claude", "codex"}

    def fake_which(binary):
        return f"/fake/{binary}" if binary in installed else None

    monkeypatch.setattr("shutil.which", fake_which)
    proposed = propose_roster()
    ids = [p.id for p in proposed]
    assert "peer-a-codex" in ids
    assert not any("gemini" in x for x in ids)


def test_drive_research_creates_focus_and_writes_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = init_paircode(tmp_path)
    # Configure one fake peer
    write_peers(state, [{"id": "peer-a-fake", "cli": "fake-cli", "mode": "full-fork"}])

    fake_outputs = {}

    def fake_run_peer(peer_id, cli, prompt, output_path, model=None, timeout_s=600):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"# {peer_id}\n\nfake research on topic", encoding="utf-8")
        fake_outputs[peer_id] = output_path
        from paircode.runner import PeerRunResult

        return PeerRunResult(
            peer_id=peer_id,
            cli=cli,
            ok=True,
            stdout="fake research",
            stderr="",
            duration_s=0.01,
            command=[cli, prompt],
        )

    with patch("paircode.drive.run_peer", side_effect=fake_run_peer):
        result = drive_research(
            topic="test topic for research",
            alpha_cli="fake-claude",
            timeout_s=5,
        )

    # Focus was created
    assert result.focus_dir.exists()
    assert result.focus_dir.name.startswith("focus-01-")
    # Both alpha and the fake peer ran
    assert result.successes == 2
    assert result.failures == 0
    # Files landed
    assert (result.focus_dir / "research" / "alpha-v1.md").exists()
    assert (result.focus_dir / "research" / "peer-a-fake-v1.md").exists()


def test_runner_writes_trace_header_even_on_failure(tmp_path: Path):
    """Even if the peer CLI isn't installed, runner writes a file-trace with error context."""
    from paircode.runner import run_peer

    out = tmp_path / "alpha-v1.md"
    result = run_peer(
        peer_id="alpha",
        cli="definitely-not-a-real-cli-xyz",
        prompt="anything",
        output_path=out,
        timeout_s=5,
    )
    assert out.exists()
    assert not result.ok
    text = out.read_text()
    assert "peer_id: alpha" in text
    assert "FAILED" in text or "not found" in text
