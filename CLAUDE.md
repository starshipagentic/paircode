# CLAUDE.md — paircode

Stable project context for AI assistants working on this codebase.

## What paircode is

Adversarial journey framework for multi-LLM peer review. One primary LLM (alpha) + any number of peer LLMs (Codex, Gemini, Ollama, …) running independent research / plan / execute stages, with structured cross-review rounds stored entirely as Markdown on disk in `.paircode/`. Installed via `pip install paircode`; user types `/paircode` in any of Claude Code, Codex, or Gemini to invoke.

## The ecosystem

paircode lives in a three-repo family:

```
starshipagentic/paircode            Python package — pypi + GitHub (this repo)
starshipagentic/paircode-codex      Codex marketplace satellite (GitHub only)
starshipagentic/paircode-gemini     Gemini extension satellite (GitHub only)
starshipagentic/cliworker           Shared CLI-invocation library (pypi + GitHub)
```

Both satellites are dumb mirrors of templates from `src/paircode/templates/`. They contain zero Python. Updated automatically by `scripts/release.py` on every paircode release.

paircode depends on `cliworker` for all subprocess work:
- `cliworker.run()` / `cliworker.run_fast()` — LLM invocations with per-CLI speed flags
- `cliworker.invoke()` — admin commands (marketplace add, extensions install) with no LLM semantics

## Install flow a user hits

```bash
pipx install paircode
paircode install   # registers /paircode in every detected LLM CLI
```

That command:
- **claude** — file-drop `~/.claude/commands/paircode.md`
- **codex** — runs `codex marketplace add starshipagentic/paircode-codex`
- **gemini** — runs `gemini extensions install https://github.com/starshipagentic/paircode-gemini --consent`

All idempotent. All with fallback messages (copy-paste command + captured stderr) if the subprocess fails.

## Release pipeline

```bash
./scripts/release.py 0.11.0      # explicit
./scripts/release.py patch       # bump last segment
./scripts/release.py --dry-run 0.11.0   # preview
```

One command bumps + commits + tags + pushes + publishes pypi + syncs both satellites + creates GitHub releases on each.

Key detail: Gemini's extensions install falls back to an interactive "git clone?" prompt if no GitHub release exists. That's why `gh release create` runs on every satellite after `starforge beam`.

## Where things live

| Concern | File |
|---|---|
| Slash command for Claude | `src/paircode/templates/claude_slash_command.md` |
| Slash command for Codex | `src/paircode/templates/codex_slash_command.md` |
| Slash command for Gemini | `src/paircode/templates/gemini_slash_command.toml` |
| LLM subprocess invocation | `src/paircode/runner.py` (→ `cliworker.run/run_fast`) |
| Slash-command installer | `src/paircode/installer.py` (→ `cliworker.invoke`) |
| `.paircode/` state schema | `src/paircode/state.py` + `src/paircode/templates/{JOURNEY,FOCUS,peers}.md` |
| Drive loop (research/plan/execute) | `src/paircode/drive.py` |
| Release pipeline | `scripts/release.py` |
| Architecture history | `diary/001-step-a-architecture.md`, `diary/002-v0.10-release-pipeline.md` |

## Tests

```bash
.venv/bin/python -m pytest -q
```

Unit + CLI smoke tests. 52 green as of v0.10.1. New CLI behavior must add a smoke test — see `tests/test_cli_smoke.py` for the parametrized help-lint + dispatch assertion patterns.

## Known paper cuts

- `__version__` in `src/paircode/__init__.py` drifts from `pyproject.toml` by 1 patch version after each release (starforge auto-bumps the toml on publish). Manual sync commit follows every release. Could be automated in release.py.
- Codex has no `codex marketplace remove` command. `paircode uninstall` edits `~/.codex/config.toml` directly — fragile but the only option until OpenAI adds the CLI.

## Conventions

- Every public CLI surface change gets a smoke test in `tests/test_cli_smoke.py`.
- Diary entries in `diary/NNN-title.md` document architecture decisions and their rationale. Include stardate, verified-state, and open paper cuts.
- Satellites never contain Python. If a change needs code, it goes in `src/paircode/`. If it's a manifest/template change, the satellites mirror automatically on next release.
- Breaking changes bump the minor version, not patch. Users installing old satellite versions should continue working until they run `paircode install` which re-registers the latest.

## License

MIT.
