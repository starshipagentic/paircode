"""Small shared helpers for paircode internals."""
from __future__ import annotations

from importlib import resources


def read_template(relative_path: str) -> str:
    """Read a file under `paircode/templates/` by relative path.

    Examples:
        read_template("FOCUS.md")
        read_template("claude/commands/paircode.md")
    """
    return (
        resources.files("paircode.templates")
        .joinpath(relative_path)
        .read_text(encoding="utf-8")
    )
