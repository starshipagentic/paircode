"""High-level loop: topic → research stage using real LLM subprocesses.

M3 scope: given a topic, ensure .paircode/ exists, open a focus, then run
ONE research round — alpha (claude) + every peer in peers.yaml all produce
cold v1 research in parallel. Writes each output to .md file on disk.

M4 will add: reviews, v2+ iterations, plan stage, execute stage.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from pathlib import Path

from paircode.runner import run_peer, PeerRunResult
from paircode.state import (
    PaircodeState,
    find_paircode,
    init_paircode,
    open_focus,
    read_peers,
)


RESEARCH_PROMPT_TEMPLATE = """You are participating in a paircode peer-review cycle.
The topic for this focus is:

    {topic}

This is the RESEARCH stage, round 1 (cold). Do NOT read any other file yet.
Produce independent research on this topic. Write a detailed markdown response
covering:

1. Problem framing — what's actually being asked?
2. Prior art — what exists in the world that's similar or informative?
3. Key questions that need to be answered before planning
4. Constraints and assumptions you're making
5. Initial directions worth exploring

Be honest, skeptical, and specific. Do not hedge. This will be peer-reviewed.
Your response will be saved verbatim to disk as a file-trace for other LLMs
to read. Write in clean markdown. No preamble, no wrap-up chatter — just the
research.
"""


@dataclass(frozen=True)
class DriveResult:
    state: PaircodeState
    focus_dir: Path
    stage: str
    peer_results: list[PeerRunResult]

    @property
    def successes(self) -> int:
        return sum(1 for r in self.peer_results if r.ok)

    @property
    def failures(self) -> int:
        return sum(1 for r in self.peer_results if not r.ok)


def _ensure_state(topic: str) -> PaircodeState:
    state = find_paircode()
    if state is None:
        state = init_paircode()
    return state


def _alpha_as_peer(topic: str) -> dict:
    """alpha = the project itself, but for drive we need a concrete runner to call.
    Default alpha to Claude since that's the most common setup; the captain can
    override via --alpha-cli.
    """
    return {"id": "alpha", "cli": "claude", "mode": "full-fork", "priority": "high"}


def drive_research(
    topic: str,
    focus_name: str | None = None,
    alpha_cli: str = "claude",
    alpha_model: str | None = None,
    timeout_s: int = 600,
) -> DriveResult:
    """Drive ONE research round on `topic`. Creates focus if needed, runs
    alpha + all peers in parallel, writes v1 outputs to disk."""
    state = _ensure_state(topic)
    focus_dir = open_focus(state, focus_name or topic, prompt=topic)

    research_dir = focus_dir / "research"
    prompt = RESEARCH_PROMPT_TEMPLATE.format(topic=topic)

    alpha = {"id": "alpha", "cli": alpha_cli, "model": alpha_model}
    peers = read_peers(state)

    jobs: list[tuple[str, str, str | None, Path]] = []
    jobs.append((alpha["id"], alpha["cli"], alpha.get("model"), research_dir / "alpha-v1.md"))
    for p in peers:
        jobs.append((p["id"], p["cli"], p.get("model"), research_dir / f"{p['id']}-v1.md"))

    results: list[PeerRunResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futures = {
            ex.submit(run_peer, pid, cli, prompt, path, model=model, timeout_s=timeout_s): pid
            for (pid, cli, model, path) in jobs
        }
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    return DriveResult(
        state=state,
        focus_dir=focus_dir,
        stage="research",
        peer_results=results,
    )
