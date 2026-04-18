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


def _make_fake_runner(record):
    from paircode.runner import PeerRunResult

    def fake_run_peer(peer_id, cli, prompt, output_path, model=None, timeout_s=600):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"# {peer_id}\n\nfake output for stage {output_path.parent.name}",
            encoding="utf-8",
        )
        record.append(peer_id)
        return PeerRunResult(
            peer_id=peer_id,
            cli=cli,
            ok=True,
            stdout=f"fake output {peer_id}",
            stderr="",
            duration_s=0.01,
            command=[cli, prompt],
        )

    return fake_run_peer


def test_drive_research_creates_focus_and_writes_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = init_paircode(tmp_path)
    write_peers(state, [{"id": "peer-a-fake", "cli": "fake-cli", "mode": "full-fork"}])

    record: list[str] = []
    with patch("paircode.drive.run_peer", side_effect=_make_fake_runner(record)):
        results = drive_research(
            topic="test topic for research",
            alpha_cli="fake-claude",
            timeout_s=5,
            rounds=1,
        )

    assert len(results) == 1
    sr = results[0]
    assert sr.focus_dir.exists()
    assert sr.version == 1
    assert sr.successes == 2  # alpha + peer-a-fake
    assert (sr.focus_dir / "research" / "alpha-v1.md").exists()
    assert (sr.focus_dir / "research" / "peer-a-fake-v1.md").exists()


def test_drive_research_multiple_rounds_does_reviews_and_revises(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = init_paircode(tmp_path)
    write_peers(state, [{"id": "peer-a-fake", "cli": "fake-cli", "mode": "full-fork"}])

    record: list[str] = []
    with patch("paircode.drive.run_peer", side_effect=_make_fake_runner(record)):
        results = drive_research(
            topic="multi-round test",
            alpha_cli="fake-claude",
            timeout_s=5,
            rounds=2,
        )

    assert len(results) == 2
    r1, r2 = results
    # Round 1: cold alpha + peer
    assert r1.version == 1
    assert len(r1.peer_results) == 2
    # Round 2: reviews + alpha revision
    assert r2.version == 2
    assert len(r2.review_results) == 1  # one peer => one review
    assert r2.alpha_revision is not None
    focus_dir = r1.focus_dir
    assert (focus_dir / "research" / "alpha-v2.md").exists()
    assert (focus_dir / "research" / "reviews" / "round-01-peer-a-fake-critiques-alpha.md").exists()


def test_drive_full_runs_all_three_stages(tmp_path: Path, monkeypatch):
    from paircode.drive import drive_full

    monkeypatch.chdir(tmp_path)
    state = init_paircode(tmp_path)
    write_peers(state, [{"id": "peer-a-fake", "cli": "fake-cli", "mode": "full-fork"}])

    record: list[str] = []
    with patch("paircode.drive.run_peer", side_effect=_make_fake_runner(record)):
        out = drive_full(
            topic="full loop test",
            alpha_cli="fake-claude",
            timeout_s=5,
            research_rounds=1,
            plan_rounds=1,
            execute_rounds=1,
        )

    assert set(out.keys()) == {"research", "plan", "execute"}
    focus_dir = out["research"][0].focus_dir
    for stage in ("research", "plan", "execute"):
        assert (focus_dir / stage / "alpha-v1.md").exists()
        assert (focus_dir / stage / "peer-a-fake-v1.md").exists()


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
