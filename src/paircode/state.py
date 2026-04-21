"""Read/write paircode state in .paircode/ directories.

The .paircode/ layout (from diary/001-step-a-architecture.md):

  .paircode/
    JOURNEY.md              ← fleet log, focus transitions
    peers.yaml              ← roster
    peers/
      peer-a-{cli}/         ← per-peer working dir (+profile.md, +code if full-fork)
    focus-01-{slug}/
      FOCUS.md
      research/
      plan/
      execute/
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from paircode.util import read_template as _read_template


PAIRCODE_DIRNAME = ".paircode"
PEERS_FILE = "peers.yaml"
JOURNEY_FILE = "JOURNEY.md"
FOCUS_FILE = "FOCUS.md"


def _now_iso() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _render(template: str, vars: dict[str, str]) -> str:
    out = template
    for k, v in vars.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "unnamed"


@dataclass(frozen=True)
class PaircodeState:
    root: Path                       # path to .paircode/ dir itself
    journey_path: Path
    peers_path: Path
    peers_dir: Path
    focus_dirs: list[Path]           # sorted by name

    @property
    def project_root(self) -> Path:
        return self.root.parent

    @property
    def active_focus(self) -> Path | None:
        """Latest focus by directory-name order (focus-NN prefix sorts naturally)."""
        return self.focus_dirs[-1] if self.focus_dirs else None

    @property
    def focus_count(self) -> int:
        return len(self.focus_dirs)


def find_paircode(start: Path | None = None) -> PaircodeState | None:
    """Walk up from `start` (or cwd) looking for .paircode/. Return None if absent."""
    if start is None:
        start = Path.cwd()
    start = start.resolve()
    for ancestor in [start, *start.parents]:
        root = ancestor / PAIRCODE_DIRNAME
        if root.is_dir():
            return load_state(root)
    return None


def load_state(root: Path) -> PaircodeState:
    focus_dirs = sorted(
        [d for d in root.iterdir() if d.is_dir() and d.name.startswith("focus-")]
    )
    return PaircodeState(
        root=root,
        journey_path=root / JOURNEY_FILE,
        peers_path=root / PEERS_FILE,
        peers_dir=root / "peers",
        focus_dirs=focus_dirs,
    )


def _peer_id(entry) -> str | None:
    """Extract `id` from a ProposedPeer or a dict-shaped peer entry."""
    if entry is None:
        return None
    if isinstance(entry, dict):
        pid = entry.get("id")
    else:
        pid = getattr(entry, "id", None)
    if not pid:
        return None
    return str(pid)


def ensure_peer_dirs(state: PaircodeState, proposed: Iterable) -> list[Path]:
    """Create .paircode/peers/{peer.id}/ for each entry. Idempotent.

    Accepts iterables of ProposedPeer dataclasses OR plain dicts (anything
    with an `id` attribute / key). Silently skips entries without a usable id.
    Returns the list of peer-dir paths that now exist (created or pre-existing).
    """
    state.peers_dir.mkdir(exist_ok=True)
    created: list[Path] = []
    for entry in proposed:
        pid = _peer_id(entry)
        if not pid:
            continue
        peer_dir = state.peers_dir / pid
        peer_dir.mkdir(exist_ok=True)
        created.append(peer_dir)
    return created


def init_paircode(project_root: Path | None = None, force: bool = False) -> PaircodeState:
    """Bootstrap .paircode/ in `project_root` (or cwd). Returns the new state.

    Also pre-creates a subdir per auto-detected peer under .paircode/peers/.
    If no peers are detected, the parent dir exists but stays empty.
    """
    if project_root is None:
        project_root = Path.cwd()
    project_root = project_root.resolve()
    root = project_root / PAIRCODE_DIRNAME
    if root.exists() and not force:
        raise FileExistsError(
            f"{root} already exists. Use --force to overwrite, or `paircode status` to inspect."
        )
    root.mkdir(parents=True, exist_ok=True)
    (root / "peers").mkdir(exist_ok=True)

    journey = _render(
        _read_template("JOURNEY.md"),
        {"project_name": project_root.name, "created_at": _now_iso()},
    )
    (root / JOURNEY_FILE).write_text(journey, encoding="utf-8")

    (root / PEERS_FILE).write_text(_read_template("peers.yaml"), encoding="utf-8")

    state = load_state(root)

    # Scaffold per-peer dirs for every auto-detected peer. Import here to
    # avoid a circular import at module load (handshake imports detect,
    # which is pure, but keeping state.py import-light is kinder).
    try:
        from paircode.handshake import propose_roster

        ensure_peer_dirs(state, propose_roster())
    except Exception:
        # Scaffolding peers is best-effort; a detect failure shouldn't
        # block bootstrap. The peers/ parent dir is already there.
        pass

    return state


def open_focus(state: PaircodeState, name: str, prompt: str | None = None) -> Path:
    """Open a new focus dir `focus-NN-{slug}/`. Returns the focus path."""
    next_num = state.focus_count + 1
    slug = _slugify(name)
    focus_dir = state.root / f"focus-{next_num:02d}-{slug}"
    if focus_dir.exists():
        raise FileExistsError(f"{focus_dir} already exists")
    focus_dir.mkdir()
    for stage in ("research", "plan", "execute", "ask"):
        (focus_dir / stage).mkdir()
        (focus_dir / stage / "reviews").mkdir()

    focus_md = _render(
        _read_template("FOCUS.md"),
        {
            "focus_name": name,
            "created_at": _now_iso(),
            "prompt": prompt or "(none given — edit this file to set the prompt)",
        },
    )
    (focus_dir / FOCUS_FILE).write_text(focus_md, encoding="utf-8")
    return focus_dir


def read_peers(state: PaircodeState) -> list[dict]:
    """Parse peers.yaml into a list of peer dicts. Returns [] if empty/missing."""
    if not state.peers_path.exists():
        return []
    data = yaml.safe_load(state.peers_path.read_text()) or {}
    return list(data.get("peers") or [])


def write_peers(state: PaircodeState, peers: Iterable[dict]) -> None:
    state.peers_path.write_text(
        yaml.safe_dump({"peers": list(peers)}, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
