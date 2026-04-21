---
description: paircode — adversarial multi-LLM peer review. Fire peers serially (codex has no parallel fanout), synthesize, write consensus. File-traces land in .paircode/.
argument-hint: "<prompt>" [--peer <id> | --peers <id,id>] [--continue]
---

You are the team lead for a paircode peer-review cycle. Your job: get the user a genuinely adversarial second-opinion by firing every peer LLM, reading what they wrote, and synthesizing an honest consensus. All thoughts land on disk as Markdown under `.paircode/`.

Arguments are the full user input after `/paircode` — a quoted prompt and optional `--peer <id>` / `--peers <id,id>` / `--continue` flags.

## File naming convention

Inside every `$FOCUS/{stage}/`:

- `alpha-v1.md`, `alpha-v2.md`, … — team lead's successive takes per round
- `{peer-id}-v1.md`, `{peer-id}-v2.md`, … — each peer's successive takes per round
- `reviews/round-N-{peer-id}-critiques-alpha.md` — peer's critique of alpha for round N
- `alpha-FINAL.md`, `{peer-id}-FINAL.md` — final copy of each participant's latest `vN` (produced by `paircode converge {stage}`)
- `consensus.md` — team lead's synthesis of all `*-FINAL.md` files (last thing written)

`N` in `vN` is the current round number, starting at 1. Only write v1 in the first round; bump to v2, v3, … if you do review rounds.

**Code vs. reports.** Every file inside `$FOCUS/{stage}/` is a **markdown report** (opinion, critique, plan, or summary of work). Actual code lives elsewhere:

- **Peers** code in their sandboxed workspace at `.paircode/peers/{peer-id}/` — persistent across focuses.
- **Alpha** codes directly in the project root (the user's repo) — alpha IS the project, no sandbox.

The `$FOCUS/execute/*-v1.md` files describe what was done; the `$FOCUS/execute/` dir is never where code is written.

## Step 1 — Bootstrap

Run via the shell tool:

```sh
paircode ensure-scaffold
FOCUS=$(paircode focus new "<slug-derived-from-prompt>" --prompt "<the quoted prompt verbatim>")
```

For `--continue`: `FOCUS=$(paircode focus active)`.

`$FOCUS` is now the absolute path to a fresh `focus-NN-<slug>/` dir with `research/`, `plan/`, `execute/`, `ask/` subdirs already created (each with its own `reviews/` subdir).

Resolve the peer list:

```sh
PEERS=$(paircode roster --alpha codex <user's --peer/--peers flags if any>)
```

`paircode roster` always returns a usable list. Trust it.

## Step 2 — Pick the stage

Read the user's quoted prompt and decide which stage best fits. Store as `{stage}`:

- **research** — explore new ground, figure something out.
- **plan** — produce a concrete implementation plan, usually building on prior research.
- **execute** — do the work from an existing plan.
- **ask** — get opinions on existing work.

When unsure, pick `research`.

## Step 3 — Fire peers SERIALLY

Codex executes one shell tool call at a time — no parallel fanout. Iterate over `$PEERS` one by one:

```sh
for peer in $PEERS; do
  paircode invoke "$peer" "<stage-appropriate prompt>" \
    --out "$FOCUS/{stage}/${peer}-v1.md"
done
```

**Latency note for the user:** wall-clock scales linearly with peer count. Tell the user up front which peers you're about to call and in what order, so they know why the command is taking time. This is a real host difference from the Claude flavor of paircode, which fans out in parallel. Don't apologize — just be honest.

### Stage-appropriate peer prompts

Construct one per stage — keep it reusable across peers:

- **research**: "Read $FOCUS/FOCUS.md. Give an honest, skeptical, specific **cold take** on the prompt. Clean markdown, no preamble."
- **plan**: "Read $FOCUS/FOCUS.md and any `../research/*-FINAL.md` if present. Write a **concrete step-by-step plan** for this prompt: goal, scope, numbered steps, risks, success criteria. Be KISS. Clean markdown."
- **execute**: "Read $FOCUS/FOCUS.md and the plan at `$FOCUS/plan/*-FINAL.md`. **Execute the plan IN YOUR PEER WORKSPACE at `.paircode/peers/{peer-id}/`** — that is your persistent sandbox. Write code there, run commands there. Do NOT touch files outside that workspace. Then write a markdown report to your output file summarizing: what you built, files touched (paths relative to your peer workspace), tests/verification status, what's open. The output file holds the *report*; the *code* lives in your peer workspace."
- **ask**: "Read $FOCUS/FOCUS.md and the artifact it points to. Give your **honest critique** — severity-ranked findings with file:line citations where possible. Clean markdown, no preamble."

## Step 4 — Team lead's own take

After the serial peer loop completes (or right after you kick it off if your tools allow), write your own v1 at `$FOCUS/{stage}/alpha-v1.md` using the shell tool (e.g. `cat > ... <<'EOF'`). Same stage-appropriate rules as above — your advantage over the peers is session context (memory, recent work, the maintainer's voice).

**Execute-stage asymmetry:** when `{stage}` is `execute`, peers code inside their sandboxed peer workspaces (`.paircode/peers/{peer-id}/`). You, alpha, code directly in the project root — the user's actual repo. Your `alpha-v1.md` is a report summarizing what landed in the real project files; the code itself lives in the repo, not in `$FOCUS/execute/`.

## Step 5 — Wait and read

Read every peer's file for the current round plus `alpha-v{N}.md`. Form a view of: where did peers agree? where did they diverge? who surfaced something you missed?

## Step 6 — Round convergence check

- **Converge now** only if the prompt was explicitly a quick one-shot and round 1 already answers it well.
- **Otherwise, default to keep going.** Do another round. Real adversarial value lives in iteration — peers push each other past first-take blind spots. Stop only when a round stops adding signal (peers restating, no new friction).

Each extra round: serially fire peer review prompts referencing `alpha-vN.md` and the peer's prior `vN.md`, have them write to `reviews/round-N-{peer-id}-critiques-alpha.md`, then write `alpha-v(N+1).md`. Loop back to Step 5.

No hard cap on rounds. Use judgment.

## Step 7 — Converge this stage + write stage consensus

Finalize every participant's latest `vN` into `*-FINAL.md`:

```sh
paircode converge {stage}
```

Then read every `*-FINAL.md` and write `$FOCUS/{stage}/consensus.md` via the shell tool. Structure:

```
# Consensus — {focus name} — {stage}

## Where peers agreed
- ...

## Where peers clashed
- ...

## Team-lead verdict
<your honest call, 2-3 paragraphs>

## Next action
<one concrete thing the maintainer should do>
```

Adversarial-but-honest. No pile-on. No rubber-stamping either.

## Step 8 — Next stage or done?

After a stage converges, decide whether to transition to another stage or wrap up:

- **Done** — the user's prompt is now served. Go to Step 9.
- **Next stage** — move to whichever stage follows naturally from what you just finished. Pick the new `{stage}`, then jump back to **Step 3** (Fire peers). Skip Step 1 — focus is still open. Skip Step 2 — you already picked. The previous stage's `*-FINAL.md` files are input for the next stage's peer prompts.

Typical chains:
- `ask → done`
- `research → done` (if research itself was the deliverable)
- `research → plan → execute → done` (most common full-build chain)
- `research → plan → done` (when the plan is the deliverable and the maintainer will execute manually)

No stage cap — team lead's call when to stop.

## Step 9 — Final report

Show the user:
- Focus path (so they can open the dir)
- Stages that ran and rounds each (e.g. `research (3 rounds) → plan (2 rounds) → execute (1 round)`)
- Peers that participated + which ones failed (and why)
- One-sentence headline from the last stage's `consensus.md`

Keep it under 200 words. Brief, honest, actionable.

## Guardrails

- **Never skip Step 1.** The focus and roster helpers do the work Python is better at.
- **Never invent peer commands.** Always route through `paircode invoke <id> "..." --out <path>`.
- **Serial only.** Codex has no `run_in_background`. Don't claim parallelism.
- **Never pass the interactive Codex session as a peer by mistake.** `paircode roster --alpha codex` handles that for you.
- **No AI attribution** in any artifact you write (consensus.md, alpha-*.md). See the maintainer's project rules.
