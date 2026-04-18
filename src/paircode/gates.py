"""Gate detection — two kinds of signals that stop a stage loop early.

1. Convergence: alpha's v_N is essentially the same as v_{N-1}. No more work to do.
2. Human gate: captain dropped a `HUMAN-GATE-*.md` file into the stage dir.

Both return a GateSignal. run_stage checks after each review+revise round and
stops if either fires.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


# If alpha_v_{N} and alpha_v_{N-1} are this similar (by SequenceMatcher ratio),
# we declare convergence. 0.95 = 95% identical character-level — conservative
# enough to only stop when almost nothing changed.
DEFAULT_CONVERGENCE_THRESHOLD = 0.95


@dataclass(frozen=True)
class GateSignal:
    stop: bool
    reason: str  # "converged" | "human_gate" | "max_rounds" | ""
    detail: str = ""


def check_convergence(
    stage_dir: Path, version: int, threshold: float = DEFAULT_CONVERGENCE_THRESHOLD
) -> GateSignal:
    """Compare alpha-v{version}.md to alpha-v{version-1}.md. If similarity
    exceeds threshold, signal stop."""
    if version < 2:
        return GateSignal(stop=False, reason="")
    curr = stage_dir / f"alpha-v{version}.md"
    prev = stage_dir / f"alpha-v{version - 1}.md"
    if not curr.exists() or not prev.exists():
        return GateSignal(stop=False, reason="")
    curr_text = curr.read_text(encoding="utf-8", errors="ignore")
    prev_text = prev.read_text(encoding="utf-8", errors="ignore")
    ratio = SequenceMatcher(None, prev_text, curr_text).ratio()
    if ratio >= threshold:
        return GateSignal(
            stop=True,
            reason="converged",
            detail=f"alpha-v{version} ~= alpha-v{version-1} (similarity {ratio:.3f} >= {threshold})",
        )
    return GateSignal(stop=False, reason="", detail=f"similarity {ratio:.3f}")


def check_human_gate(stage_dir: Path) -> GateSignal:
    """If any HUMAN-GATE-*.md file is in the stage dir, signal stop."""
    gates = sorted(stage_dir.glob("HUMAN-GATE-*.md"))
    if gates:
        return GateSignal(
            stop=True,
            reason="human_gate",
            detail=f"found {len(gates)} gate file(s): "
            + ", ".join(g.name for g in gates),
        )
    return GateSignal(stop=False, reason="")
