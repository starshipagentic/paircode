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
from importlib import resources
from pathlib import Path
from typing import Iterable

import yaml


PAIRCODE_DIRNAME = ".paircode"
PEERS_FILE = "peers.yaml"
JOURNEY_FILE = "JOURNEY.md"
FOCUS_FILE = "FOCUS.md"


def _now_iso() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_template(name: str) -> str:
    return resources.files("paircode.templates").joinpath(name).read_text(encoding="utf-8")


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


def init_paircode(project_root: Path | None = None, force: bool = False) -> PaircodeState:
    """Bootstrap .paircode/ in `project_root` (or cwd). Returns the new state."""
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

    return load_state(root)


def open_focus(state: PaircodeState, name: str, prompt: str | None = None) -> Path:
    """Open a new focus dir `focus-NN-{slug}/`. Returns the focus path."""
    next_num = state.focus_count + 1
    slug = _slugify(name)
    focus_dir = state.root / f"focus-{next_num:02d}-{slug}"
    if focus_dir.exists():
        raise FileExistsError(f"{focus_dir} already exists")
    focus_dir.mkdir()
    for stage in ("research", "plan", "execute"):
        (focus_dir / stage).mkdir()
    (focus_dir / "research" / "reviews").mkdir()
    (focus_dir / "plan" / "reviews").mkdir()

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
