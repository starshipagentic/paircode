"""Tests for stage convergence — copying latest vN to *-FINAL.md."""
from __future__ import annotations

from pathlib import Path

from paircode.converge import discover_latest_versions, seal_stage


def test_discover_latest_versions_picks_highest_per_peer(tmp_path: Path):
    (tmp_path / "alpha-v1.md").write_text("v1")
    (tmp_path / "alpha-v2.md").write_text("v2")
    (tmp_path / "alpha-v3.md").write_text("v3")
    (tmp_path / "peer-a-fake-v1.md").write_text("pa v1")
    (tmp_path / "peer-b-fake-v7.md").write_text("pb v7")
    (tmp_path / "not-versioned.md").write_text("noise")
    latest = discover_latest_versions(tmp_path)
    assert set(latest.keys()) == {"alpha", "peer-a-fake", "peer-b-fake"}
    assert latest["alpha"].name == "alpha-v3.md"
    assert latest["peer-b-fake"].name == "peer-b-fake-v7.md"


def test_seal_stage_writes_final_per_peer(tmp_path: Path):
    (tmp_path / "alpha-v1.md").write_text("v1 alpha")
    (tmp_path / "alpha-v2.md").write_text("v2 alpha")
    (tmp_path / "peer-a-v1.md").write_text("v1 peer-a")
    sealed = seal_stage(tmp_path)
    assert len(sealed) == 2
    final_alpha = tmp_path / "alpha-FINAL.md"
    assert final_alpha.exists()
    assert final_alpha.read_text() == "v2 alpha"
    final_peer = tmp_path / "peer-a-FINAL.md"
    assert final_peer.exists()
    assert final_peer.read_text() == "v1 peer-a"


def test_seal_stage_empty_dir_returns_empty(tmp_path: Path):
    assert seal_stage(tmp_path) == []
