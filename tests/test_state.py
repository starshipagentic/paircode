"""Tests for .paircode/ state bootstrap and focus opening."""
from __future__ import annotations

from pathlib import Path

import pytest

from paircode.state import (
    find_paircode,
    init_paircode,
    load_state,
    open_focus,
    read_peers,
    _slugify,
)


def test_init_creates_paircode_structure(tmp_path: Path):
    state = init_paircode(tmp_path)
    assert state.root.is_dir()
    assert state.journey_path.exists()
    assert state.peers_path.exists()
    assert state.peers_dir.is_dir()
    assert state.focus_count == 0
    assert state.active_focus is None


def test_init_refuses_if_exists_unless_force(tmp_path: Path):
    init_paircode(tmp_path)
    with pytest.raises(FileExistsError):
        init_paircode(tmp_path)
    # force=True overwrites without raising
    state = init_paircode(tmp_path, force=True)
    assert state.journey_path.exists()


def test_open_focus_creates_numbered_dir_with_stages(tmp_path: Path):
    state = init_paircode(tmp_path)
    focus_dir = open_focus(state, "ML engine baseline", prompt="KISS PHQ-9 risk")
    assert focus_dir.name == "focus-01-ml-engine-baseline"
    assert (focus_dir / "FOCUS.md").exists()
    for stage in ("research", "plan", "execute"):
        assert (focus_dir / stage).is_dir()
    assert (focus_dir / "research" / "reviews").is_dir()


def test_open_focus_increments_number(tmp_path: Path):
    state = init_paircode(tmp_path)
    open_focus(state, "first focus")
    state2 = load_state(state.root)
    open_focus(state2, "second focus")
    state3 = load_state(state.root)
    names = [d.name for d in state3.focus_dirs]
    assert names == ["focus-01-first-focus", "focus-02-second-focus"]
    assert state3.active_focus.name == "focus-02-second-focus"


def test_find_paircode_walks_up_from_subdir(tmp_path: Path):
    state = init_paircode(tmp_path)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    found = find_paircode(deep)
    assert found is not None
    assert found.root == state.root


def test_find_paircode_returns_none_when_absent(tmp_path: Path):
    assert find_paircode(tmp_path) is None


def test_read_peers_empty_by_default(tmp_path: Path):
    state = init_paircode(tmp_path)
    assert read_peers(state) == []


def test_slugify_handles_weird_chars():
    assert _slugify("ML engine baseline") == "ml-engine-baseline"
    assert _slugify("  weird!!chars??") == "weird-chars"
    assert _slugify("") == "unnamed"
    assert _slugify("x" * 100)[:40] != ""  # truncates
