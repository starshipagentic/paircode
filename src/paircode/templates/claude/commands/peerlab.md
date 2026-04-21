---
description: peerlab — alpha and peers each build in their own lab, then cross-review each other's code. Alpha is one of the peers.
---

You are the orchestrator of a `/peerlab` run. In `/peerlab`, **alpha (this Claude session) is one of the peers** — alpha builds in the project root while external peers build in their own labs at `.peerlab/<peer-id>/`. Then every participant reads every other participant's code and writes a critique. Finally you (wearing the orchestrator hat) synthesize the full cross-review into a single chat message.

This mirrors mlmodel's `/peerkickoff`: claude has `LABS/claude-kiss/`, codex has `LABS/codex-kiss/`, they build in parallel, cross-audit, iterate. Same pattern — alpha's lab is just the project root instead of a subdir.

Separate concept from `/paircode` — no focus dirs, no stages, no consensus.md. Real code in real labs + peer critiques on disk + your final synthesis in chat.

`$ARGUMENTS` is the user's raw prompt.

## Step 1 — Bootstrap (silent via Bash)

```bash
paircode peerlab ensure           # idempotent: scaffold/seed/git-init each external peer lab
PEERS=$(paircode peerlab roster --alpha claude)   # external peers (excludes alpha/claude)
```

Note: `/peerlab` is fully independent from `/paircode` — it maintains its own roster at `.peerlab/peers.yaml` and never touches `.paircode/`. You can use `/peerlab` on a project that has never seen `/paircode`.

## Step 2 — Work round (alpha + peers in parallel)

**Two streams happen concurrently.** Do NOT serialize them.

**Stream A — you, alpha:** implement `$ARGUMENTS` directly in the project root using your own tools (Read, Write, Edit, Bash, run tests). The project root IS alpha's lab. Leave your changes uncommitted in the working tree — the user reviews alpha's diff and commits manually (or discards). You are a peer building alongside others, not a distant reader.

**Stream B — external peers:** for each peer-id in `$PEERS`, spawn one subagent via Agent tool (`subagent_type=general-purpose`, `run_in_background=true`) — ALL in a single message so subagents run concurrently with each other AND with Stream A. Each subagent's prompt:

```
Monitor peer {peer-id} on the work round. Run:

  paircode peerlab invoke {peer-id} "<the user's prompt verbatim>"

That fires the peer with cwd = .peerlab/{peer-id}/ (its own lab). The peer
commits its work in its own .git before finishing.

After it returns, gather:
  1. Peer's stdout narrative.
  2. git -C .peerlab/{peer-id} log --oneline -5
  3. git -C .peerlab/{peer-id} diff HEAD~1 HEAD --stat

Report back under 400 words: peer-id, ok=yes/no, duration, 1-line summary,
git stat output.
```

Once every Stream B subagent has reported AND you've finished Stream A, proceed to Step 3.

## Step 3 — Cross-review round (everyone reads everyone)

**This is the adversarial heart of /peerlab.** Every participant — alpha AND every external peer — reads every OTHER participant's code and writes a critique. Do not skip.

If fewer than 2 participants made real progress in Step 2 (e.g., only alpha; every peer failed), you can skip Step 3 — note it in the synthesis. Otherwise:

**Stream A — you, alpha, critiquing every peer lab:** for each peer-id in `$PEERS`:
- `git -C .peerlab/<peer-id> log -p HEAD~1..HEAD` — read the full diff
- `Read` individual files inside the lab if the diff doesn't give enough context

Write your consolidated critique of the external peer labs to `.peerlab/alpha-critique.md` (at the `.peerlab/` root, NOT inside any peer's lab). Severity-ranked, file:line citations pointing at each peer's files. One section per external peer. Don't pile on, don't rubber-stamp.

**Stream B — each external peer, critiquing alpha + siblings:** for each peer-id in `$PEERS`, spawn a subagent (Agent tool, `run_in_background=true`) — ALL in one message, parallel to Stream A. Each subagent's prompt:

```
Monitor peer {peer-id} on the cross-review round. Run:

  paircode peerlab invoke {peer-id} "You already committed your own work
  in your lab (your cwd). Now cross-review every OTHER participant:

  (1) Alpha's work is at the project root. From your cwd that's ../../ .
      Read what alpha did — either:
        git -C ../../ diff HEAD            (if alpha's changes are uncommitted — usually the case)
        git -C ../../ log --oneline -5 + diff HEAD~1 HEAD   (if alpha committed)
      Then Read the specific files alpha touched.

  (2) Sibling peer labs are at ../<other-peer-id>/ . For each:
        git -C ../<other-peer-id> log -p HEAD~1..HEAD

  Write CRITIQUES.md in your own cwd (your own lab) with one section per
  participant reviewed. Include alpha. Severity-ranked. file:line citations
  pointing at the OTHER participant's files. Don't pile on, don't rubber-stamp.

    git add CRITIQUES.md
    git commit -m 'cross-review'"

After it returns, verify .peerlab/{peer-id}/CRITIQUES.md exists with a
non-trivial section for alpha plus each sibling. Report back under 300
words: peer-id, ok=yes/no, duration, 1-line summary of whose code this
peer found most/least convincing.
```

Wait for Stream A AND every Stream B subagent before Step 4.

## Step 4 — Synthesize (one message to user, ≤300 words)

Read the full cross-review:
- `.peerlab/alpha-critique.md` — your own critique of the peer labs
- Each `.peerlab/<peer-id>/CRITIQUES.md` — each peer's critique of alpha + siblings
- Alpha's own work in the project root (you remember; you did it in Step 2)
- Each peer's work diff (already gathered in Step 2)

Synthesize with the peers' voices, not just yours:

- **Implementation summaries** — alpha's approach in project root, each peer's approach in its lab. 1–2 lines each.
- **What peers said about alpha** — pull the sharpest findings from each peer's CRITIQUES.md about YOUR work. Quote them, don't paraphrase away the teeth.
- **What alpha said about peers** — reference your alpha-critique.md findings.
- **Cross-cutting themes** — where did critiques converge? That's high-signal consensus.
- **Head-to-head** — which implementation won, informed by the cross-review? Don't play favorites, don't hedge.
- **Next action** — merge a peer's pattern into alpha? Adjust alpha's implementation based on a peer's critique? Fire a peer to self-heal based on alpha's critique? Recommend; user decides.

No focus dirs, no consensus.md file. Just your synthesis as the chat reply.

## Guardrails

- **Alpha IS a peer.** You build in project root during Step 2 — not sitting out.
- **Uncommitted changes in project root stay uncommitted.** User reviews alpha's diff + commits manually. Do NOT `git add` or `git commit` in the project root as part of `/peerlab`.
- **External peers commit inside their own labs** — their `.git/` is isolated, `.peerlab/` is gitignored from the outer repo.
- **Fire every external peer** unless the user's prompt explicitly names `--peer`/`--peers`. Watchdog caps silent hangs at ~32s.
- **Do not skip Step 3** unless fewer than 2 participants succeeded in Step 2. Cross-review is the point.
- **No AI attribution** in any artifact you write (alpha-critique.md, chat synthesis). See the maintainer's CLAUDE.md.
