"""Detect installed LLM CLIs and their config directories."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliInfo:
    name: str
    binary: str
    binary_path: Path | None
    config_dir: Path
    installed: bool
    install_hint: str  # what to tell the user if they want to install this CLI


KNOWN_CLIS: dict[str, tuple[str, Path, str]] = {
    # name: (binary, config_dir, install_hint)
    "claude": (
        "claude",
        Path.home() / ".claude",
        "Install Claude Code: https://claude.com/product/claude-code",
    ),
    "codex": (
        "codex",
        Path.home() / ".codex",
        "Install Codex CLI: `npm i -g @openai/codex`",
    ),
    "gemini": (
        "gemini",
        Path.home() / ".gemini",
        "Install Gemini CLI: `npm i -g @google/gemini-cli`",
    ),
}


def detect_all() -> dict[str, CliInfo]:
    """Return a dict of name -> CliInfo for every known LLM CLI we care about."""
    result: dict[str, CliInfo] = {}
    for name, (binary, config_dir, hint) in KNOWN_CLIS.items():
        found = shutil.which(binary)
        result[name] = CliInfo(
            name=name,
            binary=binary,
            binary_path=Path(found) if found else None,
            config_dir=config_dir,
            installed=bool(found),
            install_hint=hint,
        )
    return result
