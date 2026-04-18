# Changelog

## 0.8.0 — delegate CLI invocation to cliworker, fix codex installer

Major refactor: `paircode.runner` now delegates subprocess invocation to
[`cliworker`](https://pypi.org/project/cliworker/). One place to own the
CLI-calling quirks, for paircode + navcom + anything else.

### What paircode inherits for free

- **CLAUDE_FAST flags** when `run_peer(..., fast=True)` — 18s cold start → ~4s
- **Gemini MCP strip-and-restore** automatic during gemini invocations
- **Subscription-first** by default (API keys stripped unless `paid_ok=True`)
- **Skip-cache** for broken engines (1h TTL, same for all orchestrators)
- **Friendly ollama error** when the model isn't pulled (points at the exact
  `ollama pull gemma3:4b` command)

### Breaking fix — codex installer

Previous versions wrote `~/.codex/rules/paircode.rules` as markdown. Codex
parses `rules/*.rules` files as Starlark and our markdown broke its rule
loader. From v0.8.0:

- `paircode install` no longer writes to `~/.codex/rules/`.
- `install_codex` is a no-op — codex has no slash-command system, and users
  invoke `paircode` from their shell directly.
- `install_all()` also *cleans up* any legacy broken `~/.codex/rules/paircode.rules`
  file left over from older versions. Affected users get silent cleanup on
  next install.
- Gemini installer also became a no-op (skill registration deferred to v0.9+).
- Only `claude` gets a real file written: `~/.claude/commands/paircode.md`.

### New dependency

- `cliworker>=0.7.1` in `pyproject.toml`.

### Tests

49 green (22 new). New coverage in `tests/test_cli_smoke.py`:
- Parametrized help-lint across every subcommand
- `test_runner_imports_cliworker` (regression guard against reverting the delegation)
- `test_run_peer_wraps_cliworker_result` — runner returns proper PeerRunResult
- `test_run_peer_with_failure_still_writes_trace` — file-trace on failure path
- `test_run_peer_fast_kwarg_passes_through` — fast=True reaches cliworker
- `test_installer_returns_noop_for_codex_not_installed_file` — no broken file
- `test_install_cleans_legacy_codex_rules_file` — upgrade-path cleanup
- `test_init_creates_paircode_dir`, `test_status_finds_paircode_dir` — dispatch smoke

## 0.5.0 — M5: seal + JOURNEY + stage-progress status
- `paircode seal {research|plan|execute}` copies each peer's latest versioned output to `{peer}-FINAL.md`.
- `paircode focus <name>` now updates `JOURNEY.md` (sets active focus, appends history row).
- `paircode status` per-focus stage table with version count + sealed indicator.

## 0.4.0 — M4: full loop (research → plan → execute with peer reviews)
- `paircode stage {research|plan|execute} --rounds N` drives one stage for N rounds on the active focus.
- Round 1 = cold v1 for alpha + every peer in parallel.
- Rounds 2+ = each peer reviews alpha's v_N, alpha reads all reviews and writes v_{N+1}.
- `paircode drive "<topic>"` runs the full research → plan → execute loop; `--research-only` or per-stage `--research-rounds` / `--plan-rounds` / `--execute-rounds` flags for cost control.

## 0.3.0 — M3: handshake + drive (research stage)
- `paircode handshake` detects installed CLIs, proposes a peer roster.
- `paircode handshake --write` saves roster to `.paircode/peers.yaml`.
- `paircode drive "<topic>"` real subprocess invocation of `claude -p`, `codex exec`, `gemini -p`, `ollama run`.
- Per-peer timeouts, file-trace header on every output (peer_id/cli/model/duration/ok).

## 0.2.0 — M2: state + init + status
- `.paircode/` scaffold (JOURNEY.md, peers.yaml, peers/ dir, numbered focus dirs).
- `paircode init`, `paircode status`, `paircode focus <name>`.
- `state.find_paircode()` walks up the tree to find `.paircode/` from anywhere.

## 0.1.0 — M1: install across Claude/Codex/Gemini
- `paircode install` registers `/paircode` in every detected LLM CLI:
  - Claude Code: `~/.claude/commands/paircode.md`
  - Codex: `~/.codex/rules/paircode.rules`
  - Gemini: `~/.gemini/paircode.md`
- `paircode uninstall` cleans up.

## 0.0.1 — scaffold
- Package layout, pypi metadata, click CLI skeleton, initial diary.
