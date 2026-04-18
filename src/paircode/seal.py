"""Seal a stage — copy the latest version per peer to {peer}-FINAL.md.

Sealing is the declarative exit signal for a stage. Once alpha-FINAL.md and
each peer's *-FINAL.md exist, the stage is considered complete and the next
stage can consume its outputs.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


VERSION_RE = re.compile(r"^(?P<peer>[a-z0-9][a-z0-9-]*?)-v(?P<version>\d+)\.md$")


@dataclass(frozen=True)
class SealedFile:
    peer_id: str
    source: Path
    final: Path


def discover_latest_versions(stage_dir: Path) -> dict[str, Path]:
    """Walk a stage dir, group files by peer_id, return peer_id → highest-version file."""
    latest: dict[str, tuple[int, Path]] = {}
    for p in stage_dir.iterdir():
        if not p.is_file() or not p.name.endswith(".md"):
            continue
        m = VERSION_RE.match(p.name)
        if not m:
            continue
        peer_id = m.group("peer")
        version = int(m.group("version"))
        if peer_id not in latest or version > latest[peer_id][0]:
            latest[peer_id] = (version, p)
    return {pid: path for pid, (_, path) in latest.items()}


def seal_stage(stage_dir: Path) -> list[SealedFile]:
    """For each peer in the stage, copy their highest-version file to {peer}-FINAL.md.

    Idempotent: re-running re-seals to the current latest. No-op if no versioned
    files found.
    """
    sealed: list[SealedFile] = []
    for peer_id, src in discover_latest_versions(stage_dir).items():
        final_path = stage_dir / f"{peer_id}-FINAL.md"
        shutil.copy2(src, final_path)
        sealed.append(SealedFile(peer_id=peer_id, source=src, final=final_path))
    return sealed
