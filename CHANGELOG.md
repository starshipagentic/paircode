# Changelog

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
