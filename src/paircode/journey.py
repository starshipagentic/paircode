"""Update JOURNEY.md as focuses open/close."""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from paircode.state import PaircodeState


_HISTORY_HEADER_RE = re.compile(r"^## History\s*$", re.MULTILINE)
_HISTORY_TABLE_RE = re.compile(
    r"\| # \| Focus \| Opened \| Closed \| Iterations \| Result \|\n\|[-|\s]+\|\n"
)
_ACTIVE_FOCUS_RE = re.compile(
    r"## Active focus\s*\n\n(.+?)\n\n##", re.DOTALL
)


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def note_focus_opened(state: PaircodeState, focus_name: str) -> None:
    """Update JOURNEY.md: set active focus, append history row."""
    j = state.journey_path
    if not j.exists():
        return
    text = j.read_text(encoding="utf-8")

    # Replace the "Active focus" section
    new_active = f"## Active focus\n\n**{focus_name}** — opened {_now()}\n\n##"
    text = _ACTIVE_FOCUS_RE.sub(new_active, text, count=1)

    # Append to history table
    history_match = _HISTORY_TABLE_RE.search(text)
    if history_match:
        # Count existing rows in history table
        rest = text[history_match.end():]
        existing_rows = rest.split("\n\n")[0]
        row_count = len([r for r in existing_rows.split("\n") if r.startswith("|")])
        new_row = f"| {row_count + 1} | {focus_name} | {_now()} | — | 0 | — |\n"
        text = text[:history_match.end()] + new_row + text[history_match.end():]

    j.write_text(text, encoding="utf-8")


def note_focus_closed(state: PaircodeState, focus_name: str, iterations: int, result: str) -> None:
    """Update JOURNEY.md: mark the focus row as closed with iteration count + result."""
    j = state.journey_path
    if not j.exists():
        return
    text = j.read_text(encoding="utf-8")
    # Find row for this focus and update its Closed/Iterations/Result columns
    pattern = re.compile(
        rf"(\| \d+ \| {re.escape(focus_name)} \| [^|]+\| )—( \| )0( \| )—( \|)"
    )
    text = pattern.sub(
        rf"\g<1>{_now()}\g<2>{iterations}\g<3>{result}\g<4>",
        text,
        count=1,
    )
    j.write_text(text, encoding="utf-8")
