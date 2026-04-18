---
description: Run paircode — adversarial journey framework for LLM peer review. Bootstraps .paircode/ if missing, otherwise advances the active focus.
---

You have access to the `paircode` CLI. It's a Python tool that orchestrates multi-LLM peer review (research → plan → execute) with file-traces on disk.

Behavior:

1. **Parse `$ARGUMENTS`.** Everything after `/paircode` is passed as CLI args. If empty, run `paircode` with no args (it prints status or bootstraps).
2. **Run the CLI.** Invoke `paircode $ARGUMENTS` via Bash. Capture stdout and stderr.
3. **Relay output to the user.** Show what paircode printed. If it asked a question (e.g., "accept proposed roster? y/n"), the user answers in the next turn and you pass their answer back via `paircode` again.
4. **If `paircode` spawns its own LLM subprocesses** (for research/plan/execute stages), it handles that internally — you don't need to manage the loop. Just relay status updates back to the captain.
5. **If the user's intent was a topic-level drive** (e.g., `/paircode "build a widget thing"`), invoke `paircode drive "<topic>"`.

Common subcommands you'll see:
- `paircode install` — register /paircode in Claude/Codex/Gemini (user already ran it if this command exists)
- `paircode status` — summarize .paircode/ state in cwd
- `paircode handshake` — detect installed LLM CLIs, propose peer roster
- `paircode focus <name>` — open a new focus inside .paircode/
- `paircode stage {research|plan|execute}` — run one peer-review round at that stage
- `paircode drive "<topic>"` — high-level: open focus, run research → plan → execute sequentially

Always show the captain what happened. Brief, honest, actionable.
