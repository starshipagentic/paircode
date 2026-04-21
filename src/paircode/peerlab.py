"""Per-peer independent labs — each peer owns a parallel implementation
of the project, with its own `.git/` for independent history.

Laid out under `.peerlab/<peer-id>/` at the project root, gitignored from
the outer repo. Seeding is one-time on first creation (rsync from project
root minus a standard exclude list). After that, each peer's lab evolves
independently — the peer commits, diffs, experiments in its own git.

Used by the `/peerlab` slash command (separate concept from `/paircode`):
team lead fires each peer with cwd = its lab, peers do real work and commit,
team lead reads the resulting diffs and synthesizes.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from paircode.state import PaircodeState, read_peers


PEERLAB_DIRNAME = ".peerlab"

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


@dataclass(frozen=True)
class EnsureResult:
    peer_id: str
    lab_path: Path
    status: str  # "created" | "already-exists" | "missing-id"


# ---------------------------------------------------------------------------
# Helpers — gitignore, rsync, git init, initial commit
# ---------------------------------------------------------------------------

def ensure_gitignore(project_root: Path) -> bool:
    """Append `.peerlab/` to outer .gitignore if not already present.

    Returns True if the line was added (or the file was created), False if
    it was already there.
    """
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


def _rsync_project(src: Path, dst: Path, excludes: Iterable[str] = SEED_EXCLUDES) -> None:
    """Copy src → dst with standard excludes. Uses rsync if available, falls
    back to `shutil.copytree` with an ignore function."""
    dst.mkdir(parents=True, exist_ok=True)
    rsync = shutil.which("rsync")
    if rsync:
        args = [rsync, "-a"]
        for e in excludes:
            args.extend(["--exclude", e])
        args.extend([str(src) + "/", str(dst) + "/"])
        subprocess.run(args, check=True)
        return

    # Pure-Python fallback: copytree with an ignore func.
    exclude_set = set(excludes)

    def _ignore(_directory: str, names: list[str]) -> list[str]:
        ignored = []
        for n in names:
            # Match exact name or a simple *-prefix/suffix wildcard
            if n in exclude_set:
                ignored.append(n)
                continue
            for pat in exclude_set:
                if pat.startswith("*") and n.endswith(pat[1:]):
                    ignored.append(n); break
                if pat.endswith("*") and n.startswith(pat[:-1]):
                    ignored.append(n); break
        return ignored

    # copytree fails if dst exists — but our dst was just mkdir'd.
    # Remove empty dst and let copytree re-create.
    if dst.exists() and not any(dst.iterdir()):
        dst.rmdir()
    shutil.copytree(src, dst, ignore=_ignore)


def _git_init(lab: Path) -> None:
    """`git init` inside `lab/`. No-op if already inited."""
    if (lab / ".git").exists():
        return
    # Try modern flag first, fall back for older git.
    result = subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=main", str(lab)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not (lab / ".git").exists():
        subprocess.run(["git", "init", "--quiet", str(lab)], check=True)


def _git_initial_commit(lab: Path, message: str = "initial seed from project root") -> bool:
    """Stage everything + commit. Returns True if a commit was made.

    Sets local-only user.name/email (doesn't touch global git config) so the
    commit is authored even on machines without a global identity.
    """
    if not any(lab.iterdir()):
        return False
    # Local git config — scoped to this repo
    subprocess.run(["git", "-C", str(lab), "config", "user.name", "paircode-peerlab"], check=False)
    subprocess.run(["git", "-C", str(lab), "config", "user.email", "peerlab@paircode.local"], check=False)
    subprocess.run(["git", "-C", str(lab), "add", "-A"], check=False)
    # Commit only if there's something staged
    diff_check = subprocess.run(
        ["git", "-C", str(lab), "diff", "--cached", "--quiet"],
        check=False,
    )
    if diff_check.returncode == 0:
        return False  # nothing staged
    subprocess.run(
        ["git", "-C", str(lab), "commit", "--quiet", "-m", message],
        check=False,
    )
    return True


# ---------------------------------------------------------------------------
# Public — ensure per-peer labs
# ---------------------------------------------------------------------------

def ensure_peer_labs(state: PaircodeState) -> list[EnsureResult]:
    """Scaffold `.peerlab/<peer-id>/` for every peer in `peers.yaml`.

    Idempotent. On first creation of a lab:
    - mkdir `.peerlab/<peer-id>/`
    - rsync project root → lab (minus SEED_EXCLUDES)
    - `git init` inside lab (own repo)
    - initial commit so HEAD exists → peers can `git diff HEAD~1` immediately

    On subsequent calls: skip labs that already have `.git/` — never re-seed.
    Also ensures the outer `.gitignore` contains `.peerlab/` so the outer repo
    doesn't accidentally track peer labs.
    """
    project_root = state.project_root
    peerlab_root = project_root / PEERLAB_DIRNAME
    peerlab_root.mkdir(exist_ok=True)

    ensure_gitignore(project_root)

    results: list[EnsureResult] = []
    for p in read_peers(state):
        pid = p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
        if not pid:
            results.append(EnsureResult(peer_id="?", lab_path=peerlab_root, status="missing-id"))
            continue
        lab = peerlab_root / pid
        if (lab / ".git").exists():
            results.append(EnsureResult(peer_id=pid, lab_path=lab, status="already-exists"))
            continue
        lab.mkdir(exist_ok=True)
        # Seed from project root (might be empty for greenfield — rsync handles fine)
        _rsync_project(project_root, lab)
        _git_init(lab)
        _git_initial_commit(lab, message="initial seed from project root")
        results.append(EnsureResult(peer_id=pid, lab_path=lab, status="created"))
    return results


def peer_lab_path(state: PaircodeState, peer_id: str) -> Path:
    """Return the absolute lab path for a peer id. Does not create."""
    return state.project_root / PEERLAB_DIRNAME / peer_id
