"""Tests for convergence + human-gate sentinel detection."""
from __future__ import annotations

from pathlib import Path

from paircode.gates import check_convergence, check_human_gate


def test_check_convergence_below_v2_is_noop(tmp_path: Path):
    # v1 alone can't be compared
    (tmp_path / "alpha-v1.md").write_text("anything")
    assert check_convergence(tmp_path, 1).stop is False


def test_check_convergence_identical_texts_fires(tmp_path: Path):
    text = "# plan\n\nstep 1\nstep 2\nstep 3\n"
    (tmp_path / "alpha-v1.md").write_text(text)
    (tmp_path / "alpha-v2.md").write_text(text)
    signal = check_convergence(tmp_path, 2)
    assert signal.stop is True
    assert signal.reason == "converged"


def test_check_convergence_different_texts_does_not_fire(tmp_path: Path):
    (tmp_path / "alpha-v1.md").write_text("# plan\n\nstep 1\n")
    (tmp_path / "alpha-v2.md").write_text("# plan\n\nstep A\nstep B\nstep C\n" * 10)
    signal = check_convergence(tmp_path, 2)
    assert signal.stop is False


def test_check_convergence_respects_custom_threshold(tmp_path: Path):
    (tmp_path / "alpha-v1.md").write_text("hello world " * 100)
    (tmp_path / "alpha-v2.md").write_text("hello world " * 100 + "extra")
    # Very strict threshold — expect NOT to fire (tiny diff still < 1.0)
    assert check_convergence(tmp_path, 2, threshold=1.0).stop is False
    # Loose threshold — expect to fire
    assert check_convergence(tmp_path, 2, threshold=0.5).stop is True


def test_check_human_gate_empty_dir(tmp_path: Path):
    assert check_human_gate(tmp_path).stop is False


def test_check_human_gate_detects_sentinel(tmp_path: Path):
    (tmp_path / "HUMAN-GATE-stop-and-review.md").write_text("pause: I want to review")
    signal = check_human_gate(tmp_path)
    assert signal.stop is True
    assert signal.reason == "human_gate"
    assert "stop-and-review" in signal.detail
