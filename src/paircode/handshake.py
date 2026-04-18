"""Handshake: detect installed CLIs and propose a peer roster for peers.yaml.

alpha is always implicit (= the project itself), so handshake proposes only
the peers. The captain can edit peers.yaml before running the first stage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from paircode.detect import detect_all


@dataclass(frozen=True)
class ProposedPeer:
    id: str
    cli: str
    mode: str
    priority: str
    notes: str = ""


# Default ranking of peers when auto-proposing a roster.
# Alpha is typically Claude (the primary LLM the captain is already using),
# so Claude is skipped here — peers are the other voices.
_PEER_RANK: list[tuple[str, str, str, str]] = [
    # (cli, default_mode, priority, notes)
    ("codex", "full-fork", "high", "Second opinion, good for silent-agreement hunts"),
    ("ollama", "full-fork", "medium", "Local unlimited; good if a capable model is pulled"),
    ("gemini", "opinion-only", "low", "Free tier — use for quick opinions, not full forks"),
]


def propose_roster() -> list[ProposedPeer]:
    """Scan installed CLIs, return a ranked list of peers to populate peers.yaml."""
    detected = detect_all()
    proposed: list[ProposedPeer] = []
    peer_letter = ord("a")
    for cli, default_mode, priority, notes in _PEER_RANK:
        info = detected.get(cli)
        if info and info.installed:
            proposed.append(
                ProposedPeer(
                    id=f"peer-{chr(peer_letter)}-{cli}",
                    cli=cli,
                    mode=default_mode,
                    priority=priority,
                    notes=notes,
                )
            )
            peer_letter += 1
    return proposed


def proposed_as_yaml_dicts(proposed: list[ProposedPeer]) -> list[dict]:
    return [asdict(p) for p in proposed]
