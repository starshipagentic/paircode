"""Install paircode's slash command / rules into the detected LLM CLIs.

Strategy per CLI:
  - Claude Code: write `~/.claude/commands/paircode.md` (user-level global slash command).
  - Codex: write `~/.codex/prompts/paircode.md` if codex supports it, otherwise write
    a rules snippet at `~/.codex/rules/paircode.rules` that gets picked up as context.
  - Gemini: no global slash-command primitive; install as a skill via `gemini skills install`
    or write an extension manifest. Fallback: print instructions to invoke `paircode` from shell.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from paircode.detect import detect_all, CliInfo


@dataclass(frozen=True)
class InstallResult:
    cli_name: str
    action: str  # "installed", "skipped", "failed"
    path: Path | None
    message: str


def _read_template(name: str) -> str:
    return resources.files("paircode.templates").joinpath(name).read_text(encoding="utf-8")


def install_claude(info: CliInfo) -> InstallResult:
    if not info.installed:
        return InstallResult(
            cli_name="claude",
            action="skipped",
            path=None,
            message=f"claude CLI not on PATH. {info.install_hint}",
        )
    commands_dir = info.config_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    target = commands_dir / "paircode.md"
    template = _read_template("claude_slash_command.md")
    target.write_text(template, encoding="utf-8")
    return InstallResult(
        cli_name="claude",
        action="installed",
        path=target,
        message=f"Wrote /paircode slash command to {target}. Use it from any Claude Code session.",
    )


def install_codex(info: CliInfo) -> InstallResult:
    if not info.installed:
        return InstallResult(
            cli_name="codex",
            action="skipped",
            path=None,
            message=f"codex CLI not on PATH. {info.install_hint}",
        )
    # Codex doesn't have a user-facing slash-command dir; we write a rules snippet
    # that codex reads as context in every session. This is graceful fallback.
    rules_dir = info.config_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "paircode.rules"
    template = _read_template("codex_rules.md")
    target.write_text(template, encoding="utf-8")
    return InstallResult(
        cli_name="codex",
        action="installed",
        path=target,
        message=(
            f"Wrote paircode rules to {target}. Codex will see paircode as an "
            "available tool in its context. Invoke via `codex exec 'paircode ...'`."
        ),
    )


def install_gemini(info: CliInfo) -> InstallResult:
    if not info.installed:
        return InstallResult(
            cli_name="gemini",
            action="skipped",
            path=None,
            message=f"gemini CLI not on PATH. {info.install_hint}",
        )
    # Gemini CLI exposes `gemini skills install <source>`, but we don't want to
    # depend on the gemini binary being on PATH at install time. Instead, we
    # document the invocation pattern: gemini users call paircode from shell or
    # via a skill installed manually. Write a reminder file at ~/.gemini/paircode.md.
    info.config_dir.mkdir(parents=True, exist_ok=True)
    target = info.config_dir / "paircode.md"
    template = _read_template("codex_rules.md")  # same "you have paircode CLI" content
    target.write_text(template, encoding="utf-8")
    return InstallResult(
        cli_name="gemini",
        action="installed",
        path=target,
        message=(
            f"Wrote paircode reference to {target}. Gemini users: invoke via "
            "`gemini -p 'run paircode status'` or from shell directly. Full "
            "skill-registration support lands in a later release."
        ),
    )


def install_all() -> list[InstallResult]:
    detected = detect_all()
    installers = {
        "claude": install_claude,
        "codex": install_codex,
        "gemini": install_gemini,
    }
    results: list[InstallResult] = []
    for name, info in detected.items():
        installer = installers.get(name)
        if not installer:
            continue
        try:
            results.append(installer(info))
        except Exception as exc:  # pragma: no cover — defensive
            results.append(
                InstallResult(
                    cli_name=name,
                    action="failed",
                    path=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def uninstall_all() -> list[InstallResult]:
    """Remove paircode entries from every known CLI config dir (idempotent)."""
    results: list[InstallResult] = []
    paths = [
        (Path.home() / ".claude" / "commands" / "paircode.md", "claude"),
        (Path.home() / ".codex" / "rules" / "paircode.rules", "codex"),
        (Path.home() / ".gemini" / "paircode.md", "gemini"),
    ]
    for path, cli_name in paths:
        if path.exists():
            path.unlink()
            results.append(
                InstallResult(
                    cli_name=cli_name,
                    action="installed",  # we removed it
                    path=path,
                    message=f"Removed {path}",
                )
            )
        else:
            results.append(
                InstallResult(
                    cli_name=cli_name,
                    action="skipped",
                    path=path,
                    message=f"Nothing to remove at {path}",
                )
            )
    return results
