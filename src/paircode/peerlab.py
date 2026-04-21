"""Per-peer independent labs — each peer owns a parallel implementation
of the project, with its own `.git/` for independent history.

**Fully independent from `/paircode`.** `/peerlab` maintains its own state
under `.peerlab/` at the project root:

  .peerlab/
    peers.yaml              # peerlab's own roster
    alpha-critique.md       # alpha's cross-review output (optional, written by slash command)
    peer-a-codex/           # external peer lab (full parallel implementation, own .git)
    peer-b-gemini/
    ...

`/peerlab` does NOT read or write `.paircode/`. If you use both `/paircode`
and `/peerlab`, each maintains its own roster independently. That's
intentional — `/peerlab` is designed to be useful as a standalone concept.

Architecture: **alpha (the interactive LLM session, e.g. Claude Code) is
itself a peer**. Alpha's "lab" is the project root — alpha codes directly
in the real repo. This module manages the EXTERNAL peer labs (codex,
gemini, ollama, ...). During cross-review every participant reads every
other participant's code.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


PEERLAB_DIRNAME = ".peerlab"
PEERLAB_PEERS_FILE = "peers.yaml"

SEED_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".peerlab",
    ".paircode",
    "__pycache__",
    ".venv", "venv", "env", "ENV",
    "node_modules",
    ".pytest_cache", ".tox", ".mypy_cache", ".ruff_cache",
    "build", "dist", "wheels",
    "*.egg-info",
    ".DS_Store",
    ".coverage", ".coverage.*",
    "*.pyc",
    "htmlcov",
)

GITIGNORE_BLOCK_HEADER = "# peerlab — per-peer independent parallel labs"

LAB_GITIGNORE_BLOCK = """\
# peerlab defaults — python + editor junk (keep peer commits clean)
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.tox/
.coverage
.coverage.*
htmlcov/
.DS_Store
.idea/
.vscode/
*.swp
"""
LAB_GITIGNORE_MARKER = "peerlab defaults"


# ---------------------------------------------------------------------------
# PeerlabState — independent of PaircodeState
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PeerlabState:
    """`.peerlab/` state. Fully independent from `.paircode/`."""
    root: Path                    # path to .peerlab/ dir
    peers_path: Path              # .peerlab/peers.yaml

    @property
    def project_root(self) -> Path:
        return self.root.parent


@dataclass(frozen=True)
class EnsureResult:
    peer_id: str
    lab_path: Path
    status: str  # "created" | "already-exists" | "missing-id"


def find_peerlab(start: Path | None = None) -> PeerlabState | None:
    """Walk up from `start` (or cwd) looking for `.peerlab/`. Return None."""
    if start is None:
        start = Path.cwd()
    start = start.resolve()
    for ancestor in [start, *start.parents]:
        root = ancestor / PEERLAB_DIRNAME
        if root.is_dir():
            return PeerlabState(root=root, peers_path=root / PEERLAB_PEERS_FILE)
    return None


def init_peerlab(project_root: Path | None = None) -> PeerlabState:
    """Bootstrap `.peerlab/` in `project_root` (or cwd).

    Creates the dir, runs handshake to detect peer CLIs, writes a fresh
    `peers.yaml` to `.peerlab/peers.yaml` (if missing). `handshake.propose_roster`
    is pure — reads PATH, doesn't touch any paircode state on disk.
    """
    if project_root is None:
        project_root = Path.cwd()
    project_root = project_root.resolve()
    root = project_root / PEERLAB_DIRNAME
    root.mkdir(exist_ok=True)
    peers_path = root / PEERLAB_PEERS_FILE
    if not peers_path.exists():
        # Pure-function import; doesn't trigger any paircode state writes.
        from paircode.handshake import propose_roster, proposed_as_yaml_dicts

        proposed = propose_roster()
        write_peerlab_peers(peers_path, proposed_as_yaml_dicts(proposed))
    return PeerlabState(root=root, peers_path=peers_path)


def read_peerlab_peers(state: PeerlabState) -> list[dict]:
    """Parse `.peerlab/peers.yaml` into list of peer dicts. `[]` if missing."""
    if not state.peers_path.exists():
        return []
    data = yaml.safe_load(state.peers_path.read_text(encoding="utf-8")) or {}
    return list(data.get("peers") or [])


def write_peerlab_peers(peers_path: Path, peers: Iterable[dict]) -> None:
    peers_path.write_text(
        yaml.safe_dump({"peers": list(peers)}, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Outer-repo gitignore — keep `.peerlab/` out of alpha's git
# ---------------------------------------------------------------------------

def ensure_gitignore(project_root: Path) -> bool:
    """Append `.peerlab/` to outer `.gitignore` if not already present."""
    gitignore = project_root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    for line in existing.splitlines():
        s = line.strip()
        if s in (".peerlab/", ".peerlab"):
            return False
    tail = existing.rstrip()
    new_text = (tail + "\n\n" if tail else "") + GITIGNORE_BLOCK_HEADER + "\n.peerlab/\n"
    gitignore.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Per-lab helpers — rsync seed, git init, initial commit, lab .gitignore
# ---------------------------------------------------------------------------

def _rsync_project(src: Path, dst: Path, excludes: Iterable[str] = SEED_EXCLUDES) -> None:
    """Copy src → dst with standard excludes. rsync if available, else shutil."""
    dst.mkdir(parents=True, exist_ok=True)
    rsync = shutil.which("rsync")
    if rsync:
        args = [rsync, "-a"]
        for e in excludes:
            args.extend(["--exclude", e])
        args.extend([str(src) + "/", str(dst) + "/"])
        subprocess.run(args, check=True)
        return

    exclude_set = set(excludes)

    def _ignore(_directory: str, names: list[str]) -> list[str]:
        ignored = []
        for n in names:
            if n in exclude_set:
                ignored.append(n)
                continue
            for pat in exclude_set:
                if pat.startswith("*") and n.endswith(pat[1:]):
                    ignored.append(n); break
                if pat.endswith("*") and n.startswith(pat[:-1]):
                    ignored.append(n); break
        return ignored

    if dst.exists() and not any(dst.iterdir()):
        dst.rmdir()
    shutil.copytree(src, dst, ignore=_ignore)


def ensure_lab_gitignore(lab: Path) -> bool:
    """Append the peerlab-defaults .gitignore block into the lab. Idempotent."""
    gitignore = lab / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if LAB_GITIGNORE_MARKER in existing:
        return False
    new_text = (existing.rstrip() + "\n\n" if existing.strip() else "") + LAB_GITIGNORE_BLOCK
    gitignore.write_text(new_text, encoding="utf-8")
    return True


def _git_init(lab: Path) -> None:
    if (lab / ".git").exists():
        return
    result = subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=main", str(lab)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not (lab / ".git").exists():
        subprocess.run(["git", "init", "--quiet", str(lab)], check=True)


def _git_initial_commit(
    lab: Path, peer_id: str, message: str = "initial seed from project root"
) -> bool:
    """Stage everything + commit as peer_id. Returns True if a commit was made."""
    if not any(lab.iterdir()):
        return False
    subprocess.run(["git", "-C", str(lab), "config", "user.name", peer_id], check=False)
    subprocess.run(
        ["git", "-C", str(lab), "config", "user.email", f"{peer_id}@peerlab.local"],
        check=False,
    )
    subprocess.run(["git", "-C", str(lab), "add", "-A"], check=False)
    diff_check = subprocess.run(
        ["git", "-C", str(lab), "diff", "--cached", "--quiet"], check=False,
    )
    if diff_check.returncode == 0:
        return False
    subprocess.run(
        ["git", "-C", str(lab), "commit", "--quiet", "-m", message], check=False,
    )
    return True


# ---------------------------------------------------------------------------
# Public — ensure per-peer labs
# ---------------------------------------------------------------------------

def ensure_peer_labs(state: PeerlabState) -> list[EnsureResult]:
    """Scaffold `.peerlab/<peer-id>/` for every peer in `.peerlab/peers.yaml`.

    Idempotent. On first creation of a lab:
    - mkdir
    - rsync project root → lab (minus SEED_EXCLUDES)
    - drop lab .gitignore
    - `git init` inside lab
    - initial commit authored as peer_id so HEAD exists + log attributes clean

    On subsequent calls: skip labs that already have `.git/` — never re-seed.
    Also ensures the outer `.gitignore` contains `.peerlab/`.
    """
    project_root = state.project_root
    ensure_gitignore(project_root)

    results: list[EnsureResult] = []
    for p in read_peerlab_peers(state):
        pid = p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
        if not pid:
            results.append(EnsureResult(peer_id="?", lab_path=state.root, status="missing-id"))
            continue
        lab = state.root / pid
        if (lab / ".git").exists():
            results.append(EnsureResult(peer_id=pid, lab_path=lab, status="already-exists"))
            continue
        lab.mkdir(exist_ok=True)
        _rsync_project(project_root, lab)
        ensure_lab_gitignore(lab)
        _git_init(lab)
        _git_initial_commit(lab, pid, message="initial seed from project root")
        results.append(EnsureResult(peer_id=pid, lab_path=lab, status="created"))
    return results


def peer_lab_path(state: PeerlabState, peer_id: str) -> Path:
    """Return the absolute lab path for a peer id. Does not create."""
    return state.root / peer_id
