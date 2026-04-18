---
description: Run paircode — adversarial journey framework for LLM peer review. Bootstraps .paircode/ if missing, otherwise advances the active focus.
argument-hint: [SUBCOMMAND or TOPIC]
---

You have access to the `paircode` CLI. It's a Python tool that orchestrates multi-LLM peer review (research → plan → execute) with file-traces on disk.

Behavior:

1. **Parse the arguments.** Everything after `/paircode` is passed as CLI args. If empty, run `paircode` with no args (it prints status or bootstraps).
2. **Run the CLI.** Invoke `paircode <args>` via shell. Capture stdout and stderr.
3. **Relay output to the user.** Show what paircode printed.
4. **If `paircode` spawns its own LLM subprocesses** (for research/plan/execute stages), it handles that internally — just relay status updates.
5. **If the user's intent was a topic-level drive** (e.g., `/paircode "build a widget thing"`), invoke `paircode drive "<topic>"`.

Common subcommands:
- `paircode install` — register /paircode in Claude/Codex/Gemini
- `paircode status` — summarize .paircode/ state in cwd
- `paircode handshake` — detect installed LLM CLIs, propose peer roster
- `paircode focus <name>` — open a new focus
- `paircode stage {research|plan|execute}` — run one peer-review round
- `paircode drive "<topic>"` — high-level: open focus, run research → plan → execute

Always show the user what happened. Brief, honest, actionable.
