"""Drive loop: research → plan → execute stages with peer review rounds.

Each stage round consists of:
  1. Every peer (alpha + others) writes their v_N output in parallel (cold if N=1).
  2. Every peer reviews alpha's v_N and writes review-round-N-{peer}-critiques-alpha.md.
  3. Alpha reads all reviews and writes v_{N+1} (if more rounds requested).

Plan and execute stages follow the same pattern with different prompts.
Execute stage produces .md orchestration logs only (not actual code — the
full-fork peers' code still lives under .paircode/peers/peer-N-*/ and is
managed by the peer CLIs themselves, which may invoke their own tools).
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from paircode.gates import check_convergence, check_human_gate
from paircode.runner import run_peer, PeerRunResult
from paircode.state import (
    PaircodeState,
    find_paircode,
    init_paircode,
    open_focus,
    read_peers,
)


StageName = Literal["research", "plan", "execute"]


COLD_PROMPTS: dict[StageName, str] = {
    "research": """You are participating in a paircode peer-review cycle.
The topic for this focus is:

    {topic}

This is the RESEARCH stage, round 1 (cold). Produce independent research on this
topic. Write a detailed markdown response covering:

1. Problem framing — what's actually being asked?
2. Prior art — what exists that's similar or informative?
3. Key questions that need to be answered before planning
4. Constraints and assumptions you're making
5. Initial directions worth exploring

Be honest, skeptical, specific. Your response is saved verbatim to disk as a
file-trace for other LLMs to read. Clean markdown, no preamble, just research.
""",
    "plan": """You are participating in a paircode peer-review cycle.
The topic for this focus is:

    {topic}

This is the PLAN stage, round 1 (cold). The research stage has already produced
outputs you can read at .paircode/{focus}/research/*-FINAL.md or *-v{last}.md.
Based on that research (and your own judgment), produce a concrete plan:

1. Goal (one sentence)
2. Scope (what's in, what's out)
3. Steps — numbered, each actionable
4. Risks and unknowns
5. Success criteria

Be KISS. LLMs tend to overbake plans — don't. Ship small, iterate.
""",
    "execute": """You are participating in a paircode peer-review cycle.
The topic for this focus is:

    {topic}

This is the EXECUTE stage, round 1. The plan stage outputs are at
.paircode/{focus}/plan/*-FINAL.md. Execute the plan (write code, run commands,
whatever the plan prescribes). Produce a markdown summary of what you did:

1. What you built / changed / ran
2. Files touched (with paths)
3. Tests / verification status
4. What's left open or blocked

This summary becomes a file-trace. If your CLI has file-write and command-exec
tools, use them freely — just report what happened in your response.
""",
}


REVIEW_PROMPT_TEMPLATE = """You are a peer reviewer in a paircode cycle.

Read alpha's {stage} output at:

    {alpha_file}

The topic for this focus is: {topic}

Produce an honest, skeptical review of alpha's work. Rank your findings by
severity (HIGH / MEDIUM / LOW). For each finding, cite alpha's output specifically
(line numbers or quoted phrases). Be generous with problems; be stingy with praise.

Your review will be saved to {review_path} so alpha can read it in the next
iteration round. Clean markdown. No preamble — just the ranked findings.
"""


ALPHA_REVISION_PROMPT_TEMPLATE = """You are alpha in a paircode cycle, writing
version {version} of your {stage} output for the focus on:

    {topic}

Your prior version is at:

    {alpha_prior}

The peer reviews of your prior version are at:

    {reviews_list}

Read your prior version AND all the reviews. Incorporate valid criticisms,
defend positions where critics are wrong, and produce version {version}. This
is NOT a complete rewrite unless the critics are catastrophically right —
revise incrementally.

Clean markdown. No meta-commentary — just the revised output.
"""


@dataclass
class StageResult:
    focus_dir: Path
    stage: str
    version: int
    peer_results: list[PeerRunResult] = field(default_factory=list)
    review_results: list[PeerRunResult] = field(default_factory=list)
    alpha_revision: PeerRunResult | None = None

    @property
    def successes(self) -> int:
        return sum(
            1
            for r in self.peer_results + self.review_results + ([self.alpha_revision] if self.alpha_revision else [])
            if r and r.ok
        )

    @property
    def failures(self) -> int:
        return sum(
            1
            for r in self.peer_results + self.review_results + ([self.alpha_revision] if self.alpha_revision else [])
            if r and not r.ok
        )


def _ensure_state() -> PaircodeState:
    state = find_paircode()
    if state is None:
        state = init_paircode()
    return state


def _format_prompt(stage: StageName, topic: str, focus_dir: Path) -> str:
    return COLD_PROMPTS[stage].format(
        topic=topic,
        focus=focus_dir.name,
        last="1",
    )


def run_stage_cold(
    state: PaircodeState,
    focus_dir: Path,
    stage: StageName,
    topic: str,
    alpha_cli: str = "claude",
    alpha_model: str | None = None,
    timeout_s: int = 600,
) -> StageResult:
    """Run cold v1 of a stage — alpha + all peers in parallel."""
    stage_dir = focus_dir / stage
    stage_dir.mkdir(exist_ok=True)
    (stage_dir / "reviews").mkdir(exist_ok=True)
    prompt = _format_prompt(stage, topic, focus_dir)

    peers = read_peers(state)
    jobs: list[tuple[str, str, str | None, Path]] = []
    jobs.append(("alpha", alpha_cli, alpha_model, stage_dir / "alpha-v1.md"))
    for p in peers:
        jobs.append((p["id"], p["cli"], p.get("model"), stage_dir / f"{p['id']}-v1.md"))

    results: list[PeerRunResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(jobs))) as ex:
        futures = {
            ex.submit(run_peer, pid, cli, prompt, path, model=model, timeout_s=timeout_s): pid
            for (pid, cli, model, path) in jobs
        }
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    return StageResult(
        focus_dir=focus_dir,
        stage=stage,
        version=1,
        peer_results=results,
    )


def run_review_round(
    state: PaircodeState,
    focus_dir: Path,
    stage: StageName,
    topic: str,
    version: int,
    timeout_s: int = 600,
) -> list[PeerRunResult]:
    """Every peer reviews alpha's v_{version}. Writes to reviews/round-{version}-*.md."""
    stage_dir = focus_dir / stage
    reviews_dir = stage_dir / "reviews"
    reviews_dir.mkdir(exist_ok=True)
    alpha_file = stage_dir / f"alpha-v{version}.md"
    if not alpha_file.exists():
        raise FileNotFoundError(f"alpha output missing: {alpha_file}")

    peers = read_peers(state)
    jobs: list[tuple[str, str, str | None, str, Path]] = []
    for p in peers:
        review_path = reviews_dir / f"round-{version:02d}-{p['id']}-critiques-alpha.md"
        prompt = REVIEW_PROMPT_TEMPLATE.format(
            stage=stage,
            alpha_file=alpha_file,
            topic=topic,
            review_path=review_path,
        )
        jobs.append((p["id"], p["cli"], p.get("model"), prompt, review_path))

    results: list[PeerRunResult] = []
    if not jobs:
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futures = {
            ex.submit(run_peer, pid, cli, prompt, path, model=model, timeout_s=timeout_s): pid
            for (pid, cli, model, prompt, path) in jobs
        }
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    return results


def run_alpha_revision(
    state: PaircodeState,
    focus_dir: Path,
    stage: StageName,
    topic: str,
    version: int,
    alpha_cli: str = "claude",
    alpha_model: str | None = None,
    timeout_s: int = 600,
) -> PeerRunResult:
    """Alpha reads its own v_{version} and all peer reviews, writes v_{version+1}."""
    stage_dir = focus_dir / stage
    alpha_prior = stage_dir / f"alpha-v{version}.md"
    reviews_dir = stage_dir / "reviews"
    review_files = sorted(reviews_dir.glob(f"round-{version:02d}-*-critiques-alpha.md"))
    reviews_list = "\n".join(f"  - {p}" for p in review_files) or "  (no reviews)"

    prompt = ALPHA_REVISION_PROMPT_TEMPLATE.format(
        version=version + 1,
        stage=stage,
        topic=topic,
        alpha_prior=alpha_prior,
        reviews_list=reviews_list,
    )
    out_path = stage_dir / f"alpha-v{version + 1}.md"
    return run_peer(
        peer_id="alpha",
        cli=alpha_cli,
        prompt=prompt,
        output_path=out_path,
        model=alpha_model,
        timeout_s=timeout_s,
    )


def run_stage(
    topic: str,
    focus_dir: Path,
    stage: StageName,
    rounds: int = 1,
    alpha_cli: str = "claude",
    alpha_model: str | None = None,
    timeout_s: int = 600,
    state: PaircodeState | None = None,
    check_gates: bool = True,
) -> list[StageResult]:
    """Run a stage for `rounds` rounds. Round 1 is cold v1. Rounds 2+ do
    review-then-revise cycles. Stops early on convergence or human-gate
    sentinel unless check_gates=False. Returns one StageResult per round."""
    if state is None:
        state = _ensure_state()
    if rounds < 1:
        raise ValueError("rounds must be >= 1")

    stage_dir = focus_dir / stage

    # Check human gate BEFORE starting
    if check_gates:
        gate = check_human_gate(stage_dir)
        if gate.stop:
            # Still run cold v1 so we have something, then stop.
            pass

    # Round 1: cold v1
    first = run_stage_cold(
        state, focus_dir, stage, topic,
        alpha_cli=alpha_cli, alpha_model=alpha_model, timeout_s=timeout_s,
    )
    out = [first]

    # Rounds 2..N: review + revise, with gate checks between rounds
    for r in range(2, rounds + 1):
        if check_gates:
            hg = check_human_gate(stage_dir)
            if hg.stop:
                break
        prev_version = r - 1
        reviews = run_review_round(
            state, focus_dir, stage, topic, prev_version, timeout_s=timeout_s
        )
        revision = run_alpha_revision(
            state, focus_dir, stage, topic, prev_version,
            alpha_cli=alpha_cli, alpha_model=alpha_model, timeout_s=timeout_s,
        )
        out.append(StageResult(
            focus_dir=focus_dir,
            stage=stage,
            version=r,
            review_results=reviews,
            alpha_revision=revision,
        ))
        # Convergence check AFTER revision lands
        if check_gates:
            conv = check_convergence(stage_dir, r)
            if conv.stop:
                break
    return out


def drive_research(
    topic: str,
    focus_name: str | None = None,
    alpha_cli: str = "claude",
    alpha_model: str | None = None,
    timeout_s: int = 600,
    rounds: int = 1,
) -> list[StageResult]:
    """Open a focus, run research stage for `rounds` rounds."""
    state = _ensure_state()
    focus_dir = open_focus(state, focus_name or topic, prompt=topic)
    return run_stage(
        topic, focus_dir, "research",
        rounds=rounds, alpha_cli=alpha_cli, alpha_model=alpha_model,
        timeout_s=timeout_s, state=state,
    )


def drive_full(
    topic: str,
    focus_name: str | None = None,
    alpha_cli: str = "claude",
    alpha_model: str | None = None,
    timeout_s: int = 600,
    research_rounds: int = 2,
    plan_rounds: int = 2,
    execute_rounds: int = 1,
) -> dict[str, list[StageResult]]:
    """Full loop: open focus, run research + plan + execute. Returns per-stage results."""
    state = _ensure_state()
    focus_dir = open_focus(state, focus_name or topic, prompt=topic)
    results: dict[str, list[StageResult]] = {}
    for stage, rounds in (("research", research_rounds), ("plan", plan_rounds), ("execute", execute_rounds)):
        results[stage] = run_stage(
            topic, focus_dir, stage,  # type: ignore[arg-type]
            rounds=rounds, alpha_cli=alpha_cli, alpha_model=alpha_model,
            timeout_s=timeout_s, state=state,
        )
    return results
