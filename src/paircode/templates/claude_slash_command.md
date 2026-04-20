---
description: Run paircode — adversarial multi-LLM peer review with team-agents orchestration. Writes file-traces to .paircode/.
---

# /paircode — Adversarial Multi-LLM Peer Review (Team Lead)

You are the team lead. The interactive Claude session IS alpha. Peers (Codex, Gemini, Ollama, ...) run as subprocesses via `paircode invoke`. All artifacts are Markdown under `.paircode/`.

`$ARGUMENTS` holds the user's quoted prompt plus optional flags: `--peer <id>`, `--peers <id,id>`, `--continue`, `--max-rounds <N>`.

Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. No fallbacks.

---

## Phase 0: Parse + Scaffold

1. Extract the quoted prompt from `$ARGUMENTS`. If no quoted string is present and the entire argument is freeform text, treat the whole argument as the prompt.
2. Parse optional flags: `--peer <id>`, `--peers <id1,id2>`, `--continue`, `--max-rounds <N>` (default 3).
3. If no prompt at all: `AskUserQuestion` — "What do you want paircode to review?"
4. Run `paircode ensure-scaffold` via Bash. Silent on success. If it errors, stop and report.

---

## Phase 1: Focus Resolution

- Default: derive a short kebab-case slug from the prompt (max 5 words). Run:
  ```
  paircode focus new "<slug>" --prompt "<prompt>"
  ```
  Capture stdout — it prints the focus directory path (e.g. `.paircode/focus-03-rewrite-drive/`).

- If `--continue`: run `paircode focus active` and use its stdout as the focus path.

Store `FOCUS_PATH` and `FOCUS_SLUG` for later phases.

---

## Phase 2: Team Creation + Roster

```
TeamCreate(team_name: "paircode-{FOCUS_SLUG}",
           description: "paircode on: {prompt truncated to 80 chars}")
```

Get the roster:
```
paircode roster
```
One peer-id per line. Apply filter:
- If `--peer <id>`: keep only that peer. Error if missing from roster.
- If `--peers <id1,id2>`: keep only those. Error if any missing.
- Else: keep all.

If the filtered roster is empty, `TeamDelete` and stop — tell the user to run `paircode install` or edit `.paircode/peers.yaml`.

Store `PEERS` as the filtered list.

---

## Phase 3: Task Graph + Peer Spawn

Create the task dependency chain. For each `peer_id` in `PEERS`:

```
TaskCreate(title: "peer-{peer_id}-v1",
           description: "Peer {peer_id} writes v1 take on the prompt")
```
No blockers — these run in parallel.

Then the review chain:

```
TaskCreate(title: "alpha-review",
           description: "Team lead reads all peer v1s + writes alpha-vN+1",
           addBlockedBy: [<all peer-v1 task ids>])

TaskCreate(title: "seal-round",
           description: "Team lead seals each peer FINAL + writes alpha-FINAL",
           addBlockedBy: [<alpha-review task id>])

TaskCreate(title: "consensus",
           description: "Team lead writes consensus.md synthesizing all FINALs",
           addBlockedBy: [<seal-round task id>])
```

### Spawn peers in parallel

For each `peer_id` in `PEERS`:

```
Agent(name: "paircode-peer", team_name: "paircode-{FOCUS_SLUG}")
  -> "You are peer '{peer_id}'. Focus prompt follows. Write your v1 take.
      peer_id: {peer_id}
      output_path: {FOCUS_PATH}/research/{peer_id}-v1.md
      focus_dir: {FOCUS_PATH}
      peer_dir: .paircode/peers/{peer_id}
      prompt: {prompt}
      Run `paircode invoke {peer_id} \"{prompt}\" --out {FOCUS_PATH}/research/{peer_id}-v1.md`,
      verify the file wrote, then SendMessage back with ok + 1-line summary."
```

Spawn all peers in a single batch so they run truly in parallel.

---

## Phase 4: Alpha v1 (In-Session)

**You** (this Claude session) are alpha. While peers run, write your own v1:

1. `Read` the focus's `FOCUS.md` to see the rendered prompt + stage template.
2. Think cold — no peer influence yet. Write your independent take.
3. `Write` it to `{FOCUS_PATH}/research/alpha-v1.md`. Include a file-trace header:
   ```
   <!-- paircode file-trace
   focus: {FOCUS_SLUG}
   author: alpha (claude-code interactive session)
   round: 1
   -->
   ```

Do this in parallel with peers being out. Do not wait.

---

## Phase 5: Collect v1s + Converge Decision

Wait for `SendMessage` from each spawned `paircode-peer` agent. Each reports `ok: true/false`, duration, 1-line summary.

If any peer reported `ok: false`: message that peer again with the error, or skip it if retry fails twice. Note the skip in the final report.

Once all v1s are on disk (`Bash: ls {FOCUS_PATH}/research/*-v1.md`):

1. `Read` every `*-v1.md` in `{FOCUS_PATH}/research/`.
2. Decide: **converge** or **another round**?
   - Converge if peers agree on the substantive claims and alpha agrees.
   - Another round if peers disagree, reveal blind spots, or surface claims alpha missed.
3. Hard cap: `--max-rounds` (default 3). After round 3, converge regardless.

---

## Phase 6: Review Rounds (repeat until converge)

For round N+1:

### 6a. Send review prompts to each peer in parallel

For each `peer_id` still in play:

```
SendMessage(to: <peer_agent>, message:
  "Round {N+1} review. Read {FOCUS_PATH}/research/alpha-v{N}.md
   and your own {FOCUS_PATH}/research/{peer_id}-v{N}.md.
   Write your critique of alpha's take to
   {FOCUS_PATH}/reviews/round-{N}-{peer_id}-critiques-alpha.md.
   Run: paircode invoke {peer_id}
     \"<review prompt with both files inlined or cited>\"
     --out {FOCUS_PATH}/reviews/round-{N}-{peer_id}-critiques-alpha.md
   SendMessage back when done.")
```

### 6b. Wait for all review SendMessages.

### 6c. Alpha revises

1. `Read` every `round-{N}-*-critiques-alpha.md` file.
2. Write `{FOCUS_PATH}/research/alpha-v{N+1}.md` — your revised take that engages the critiques explicitly. Steel-man the peers; don't hand-wave.

### 6d. Peers revise (optional — include if you want peer-on-peer review)

For symmetry, message each peer to write `{peer_id}-v{N+1}.md` responding to alpha's revision and the other peers' critiques. Skip this step if rounds are converging fast.

Loop back to Phase 5's converge check.

---

## Phase 7: Seal Round

Close the `alpha-review` task → `seal-round` unblocks.

1. For each `peer_id`: `Bash: cp {FOCUS_PATH}/research/{peer_id}-v{N}.md {FOCUS_PATH}/{peer_id}-FINAL.md`
   (latest vN for that peer — use `ls` to find it).
2. `Write` `{FOCUS_PATH}/alpha-FINAL.md` — your sealed position. Same file-trace header, `round: FINAL`.

Close the `seal-round` task → `consensus` unblocks.

---

## Phase 8: Consensus

Read ALL `*-FINAL.md` files in `{FOCUS_PATH}/`. Write `{FOCUS_PATH}/consensus.md` as an adversarial-but-honest synthesis:

```markdown
# Consensus — {FOCUS_SLUG}

**Prompt:** {prompt}
**Peers:** {list}
**Rounds:** {N}

## Where we agreed
<substantive points every participant endorsed>

## Where we clashed
<points of genuine disagreement, attributed by peer>

## Team lead verdict
<alpha's call, with reasoning, acknowledging where peers may still be right>

## What to do next
<concrete next actions falling out of the review>
```

Close the `consensus` task.

---

## Phase 9: Teardown + Report

```
TeamDelete(team_name: "paircode-{FOCUS_SLUG}")
```

Report to user:

```
## paircode complete — {FOCUS_SLUG}

**Focus:** {FOCUS_PATH}
**Peers:** {list, skipped marked}
**Rounds:** {N}
**Consensus headline:** <one-liner from consensus.md's verdict>

**Artifacts:**
- {FOCUS_PATH}/consensus.md
- {FOCUS_PATH}/alpha-FINAL.md
- {FOCUS_PATH}/{peer}-FINAL.md  (one per peer)
- {FOCUS_PATH}/research/*.md
- {FOCUS_PATH}/reviews/*.md

Read consensus.md for the synthesized verdict.
```

---

## Abort Conditions

Stop and ask the user (then `TeamDelete` on exit) if:
- Empty filtered roster after `--peer`/`--peers` filtering
- `paircode ensure-scaffold` fails
- Same peer fails `paircode invoke` twice in a row — skip it, note in report
- Peer output files are empty or missing the file-trace header on verify
- `--max-rounds` exceeded without convergence (emit consensus anyway, flag as unresolved)

## Never

- Bypass `paircode invoke` for peer calls — it owns the file-trace header contract
- Skip writing `alpha-FINAL.md` or `consensus.md`
- Leave the team alive after the report (always `TeamDelete`)
- Add AI attribution to any artifact committed to the user's repo
