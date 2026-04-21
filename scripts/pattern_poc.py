#!/usr/bin/env python3
"""Proof-of-concept: YAML-driven stage patterns for paircode.

Status: paircode today HARDCODES four stages (research/plan/execute/ask) in
`src/paircode/state.py:open_focus` and in every slash-command template. The
pattern-template feature was designed in focus-02's consensus (see
`.paircode/focus-02-stage-pattern-templates/research/consensus.md`) but never
shipped.

This script proves the design works end-to-end as a demo, without touching
any real paircode code. If we like it, the design maps cleanly into `state.py`:

  - `src/paircode/patterns.py` (new) — what `load_pattern()` below does, plus
    user-repo override resolution (`.paircode/patterns/<name>.yaml` wins over
    bundled `src/paircode/templates/patterns/<name>.yaml`).
  - `src/paircode/state.py:open_focus` — take `pattern_name` arg, iterate over
    `pattern.stages` instead of the hardcoded tuple, stamp `flow:` into
    FOCUS.md.
  - `src/paircode/cli.py` — `paircode patterns` command, `--pattern` flag on
    `focus new`.

Run this file directly:

    ./scripts/pattern_poc.py

It will load both example patterns, print the parsed objects, and scaffold
two demo focus dirs under /tmp/ showing that different patterns produce
different on-disk layouts.
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = SCRIPT_DIR / "example_patterns"
DEMO_ROOT = Path("/tmp/paircode-pattern-poc")


# ---------------------------------------------------------------------------
# Pattern data model — mirrors what would land in src/paircode/patterns.py
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pattern:
    """A named composition of stages with optional per-stage prompt overrides."""

    name: str
    description: str
    stages: list[str]
    stage_overrides: dict[str, dict] = field(default_factory=dict)

    def prompt_for(self, stage: str, default_prompt: str) -> str:
        """Return the effective prompt for a stage — override wins over default."""
        override = self.stage_overrides.get(stage, {}).get("prompt")
        return override or default_prompt


def load_pattern(path: Path) -> Pattern:
    """Parse a YAML pattern file into a Pattern dataclass."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Pattern(
        name=data["name"],
        description=data.get("description", ""),
        stages=list(data.get("stages") or []),
        stage_overrides=dict(data.get("stage_overrides") or {}),
    )


# ---------------------------------------------------------------------------
# Pattern-driven scaffolder — mirrors what would replace the hardcoded list
# in src/paircode/state.py:open_focus
# ---------------------------------------------------------------------------

def scaffold_focus(focus_dir: Path, pattern: Pattern) -> list[Path]:
    """Create focus dir + one subdir per pattern.stages (each with reviews/).

    Returns the list of stage dirs created.
    """
    focus_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for stage in pattern.stages:
        stage_dir = focus_dir / stage
        stage_dir.mkdir(exist_ok=True)
        (stage_dir / "reviews").mkdir(exist_ok=True)
        created.append(stage_dir)

    focus_md = focus_dir / "FOCUS.md"
    focus_md.write_text(
        f"# FOCUS (pattern: {pattern.name})\n\n"
        f"{pattern.description}\n\n"
        f"stages: {', '.join(pattern.stages)}\n",
        encoding="utf-8",
    )
    return created


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _print_pattern(p: Pattern) -> None:
    print(f"  name: {p.name}")
    print(f"  description: {p.description}")
    print(f"  stages: {p.stages}")
    if p.stage_overrides:
        print(f"  stage_overrides: {list(p.stage_overrides.keys())}")
    else:
        print("  stage_overrides: (none)")


def _print_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root.parent)
        suffix = "/" if path.is_dir() else ""
        print(f"    {rel}{suffix}")


def main() -> int:
    print("=" * 72)
    print("paircode pattern-template POC")
    print("=" * 72)
    print(f"\nLoading patterns from {PATTERNS_DIR}:")
    pattern_files = sorted(PATTERNS_DIR.glob("*.yaml"))
    if not pattern_files:
        print(f"  No YAML files found at {PATTERNS_DIR}", file=sys.stderr)
        return 1

    patterns: dict[str, Pattern] = {}
    for path in pattern_files:
        p = load_pattern(path)
        patterns[p.name] = p

    print()
    for name, p in patterns.items():
        print(f"→ loaded pattern '{name}':")
        _print_pattern(p)
        print()

    print("-" * 72)
    print(f"Scaffolding demo focuses under {DEMO_ROOT}/:")
    print("-" * 72)
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)

    for i, (name, pattern) in enumerate(patterns.items(), 1):
        focus = DEMO_ROOT / f"focus-{i:02d}-demo-{name}"
        scaffold_focus(focus, pattern)
        print(f"\n✓ scaffolded {focus.name} with pattern '{name}':")
        _print_tree(focus)

    print()
    print("=" * 72)
    print("POC complete. This proves:")
    print("  1. YAML pattern files parse into a clean Pattern dataclass.")
    print("  2. stage_overrides round-trip for per-pattern prompt tuning.")
    print("  3. Focus dirs scaffold differently per pattern — no hardcoded list.")
    print()
    print("Next (real integration in paircode):")
    print("  - Move Pattern + load_pattern into src/paircode/patterns.py.")
    print("  - state.py:open_focus gains pattern_name arg, iterates pattern.stages.")
    print("  - cli.py gains `paircode patterns` + `focus new --pattern <name>`.")
    print("  - Default pattern stays 'build' (research→plan→execute) for b/c.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
