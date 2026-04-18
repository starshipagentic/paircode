# Diary 001 — Step-A architecture, complete and locked

**Stardate:** 2026-04-18
**Milestone:** step-A (understand) complete. Step-B (plan schemas + command lifecycle) next. Step-C (ship to pypi + as slash command) after.
**Sibling project that birthed this:** `~/clients/syra/mlmodel/` at tag `milestone-0.1` — 31 iterations of `/peerkickoff` between Claude and Codex on a KISS mental-health ML pipeline surfaced the meta-pattern this project generalizes.

---

## TL;DR — what paircode is

A framework for steering a software project through any number of **focuses** (goals), where each focus runs a **research → plan → execute** cycle, and every stage of every cycle is **peer-reviewed** by one "alpha" codebase plus N peer LLMs producing file-traces on disk. The captain (human architect) sets scope and taste; the LLMs author content.

Three layers, three peer modes, one hidden folder, files on disk always.

---

## Provenance — why this exists

Between 2026-04-17 and 2026-04-18, two LLMs (Claude Opus 4.7 and Codex) were run adversarially on a shared ML project:

- Each produced **independent cold research** on mental-health risk stratification.
- Each produced **5 iterated versions of a plan** (`plan1 → plan1.5`), cross-reviewing via human-mediated copy-paste.
- Human called bullshit, forced a **KISS reduction** (scope-cut gate).
- Each executed a **full-fork cold implementation** (`LABS/claude-kiss/` + `LABS/codex-kiss/`).
- `/peerkickoff` command orchestrated **31 rounds of cross-review**, surfacing ~30 silent-data-corruption defect classes that neither engine alone could catch (because cross-engine *agreement* is not the same as correctness when both share the same blind spot).

Final state at `milestone-0.1`:
- claude-kiss pytest: 74 green
- codex-kiss pytest: 66 green
- Cross-engine tier-agreement on 258/258 rows (silent-agreement-on-valid-data baseline)
- Real NHANES 2011-2018 ML baseline: AUC 0.67 SDOH-only, bit-identical MD5 reproducibility (11+ consecutive matches)
- ~30 input-contract guards landed (Excel serials, NaN/bytes/bidi/zero-width patient IDs, Arrow/Period/timedelta/tz-aware dates, fractional scores, empty-post-strip IDs, ...)

Two conclusions from that run:
1. **The *pattern* is generalizable.** Research, plan, and execute are three instances of the same peer-review engine — only the artifact type differs.
2. **The *specific implementation* (hardcoded paths, ML-specific prompts, manual copy-paste at early stages) was scaffolding**, not the thing itself. paircode is the extracted framework.

---

## The meta-pattern — named

**Adversarial journey architecture**, a.k.a. **dual-lane stage-gate with file-trace peer review and human taste-gates.**

It's a variant of the Phase-Gate model from 1980s product development, run at LLM speed with N parallel LLM lanes, each stage producing file-traces that the next stage consumes.

### Three layers

```
┌────────────────────────────────────────────────────────┐
│ JOURNEY (captain's layer)                              │
│   FOCUS-1 → FOCUS-2 → FOCUS-3 → ...                    │
│   (ML engine → claims expansion → demo site → app)     │
└──────────┬─────────────────────────────────────────────┘
           │ each FOCUS contains ↓
┌──────────▼─────────────────────────────────────────────┐
│ WORKFLOW (per-focus lifecycle)                         │
│   Research → Plan → Execute                            │
│   (each stage peer-reviewed, each stage optional)      │
└──────────┬─────────────────────────────────────────────┘
           │ each STAGE uses ↓
┌──────────▼─────────────────────────────────────────────┐
│ PEER-REVIEW ENGINE (universal primitive)               │
│   Alpha cold → peers cold →                            │
│   N rounds of cross-review with file traces →          │
│   optional human gate → FINAL per-peer                 │
└────────────────────────────────────────────────────────┘
```

The inner engine is one thing. Stage + focus + journey are all just different scales of invoking it.

---

## The universal peer-review engine

Same shape at every stage. Only the prompt and the artifact type differ:

| Stage | Alpha writes | Peers write | Exit artifact |
|---|---|---|---|
| Research | `alpha-v{N}.md` | `peer-a-v{N}.md` ... | `alpha-FINAL.md` + `peer-a-FINAL.md` ... |
| Plan | `alpha-v{N}.md` | `peer-a-v{N}.md` ... | Same naming |
| Execute | Code in project root | Code in `.paircode/peers/peer-a-codex/` (if full-fork) + review `.md` files | `iter-NNN.md` orchestration logs + `alpha-FINAL.md` summary per peer |

### Peer-review mechanics (identical at every stage)

1. **Round 0** — Alpha and all peers produce **cold, independent** versions. No one sees anyone else's output. This independence is sacred — it's what prevents anchoring.
2. **Round N (N ≥ 1)** — Each peer reads alpha's latest, writes a review file (`reviews/round-N-peer-X-critiques-alpha.md`). Alpha reads ALL peer reviews, incorporates, publishes `alpha-v{N+1}.md`. Peers optionally revise their own cold version to `peer-X-v{N+1}.md` based on what they now know.
3. **Gate check** — did human intervene (`HUMAN-GATE-*.md` file appeared)? Did we hit `MAX_ROUNDS`? Did we hit a convergence criterion (e.g., 3 consecutive rounds of no new findings)?
4. **Exit** — each peer writes their FINAL; alpha writes its FINAL *after* reading peers' FINALs (so alpha's final says "having seen everyone, here's my sealed position"); stage is closed.

---

## N-team star topology

```
            Alpha (the project itself)
           /     |      \        \
          /      |       \        \
      peer-a   peer-b   peer-c   peer-d ...
      (Codex)  (Gemini) (Ollama) (N teams)
```

**Key rule:** Peers review *alpha only*. Peers do NOT peer-review each other. This keeps review edges at O(N), not O(N²).

**Knowledge seepage:** Ideas from peer-c reach peer-a not via direct peer-c↔peer-a edge, but via alpha absorbing peer-c's review in round N, which peer-a then sees when it reads alpha-v{N+1}. Alpha is the gossip hub.

**Why Alpha is the project, not a peer:** alpha is implicit — it's the project directory itself, the captain's primary working codebase. No `team-a/` or `lane-a/` subfolder. When you `cd ~/myproject`, you are in alpha's workspace.

---

## Three peer modes

| Mode | Peer writes | Peer code location | Cost | Use case |
|---|---|---|---|---|
| **full-fork** | Own cold codebase + `.md` artifacts | `.paircode/peers/peer-N-{cli}/src/` etc. | High — peer does full implementation work | Silent-agreement hunting, safety-critical code |
| **pair-code** | Patches / proposed diffs / reviews as `.md` | No code dir — peer contributes to alpha's codebase directly | Medium | Feature work, frontend, general dev |
| **opinion-only** | Review / opinion `.md` files only | No code at all, just `.md` under focus folders | Low — cheapest mode | Budget peers, free-tier models, quick sanity checks |

**Every peer gets a folder regardless of mode.** Opinion-only peers have a mostly-empty `.paircode/peers/peer-b-gemini/` with just a `profile.md` from the handshake. Full-fork peers have a complete working codebase there. The principle is: **every LLM's every thought gets written to disk**, because that's how heterogeneous LLM tools communicate reliably across vendors, sessions, days.

---

## File-trace schema

```
~/clients/syra/mlproject/              ← project root = alpha's code
  src/, tests/, README.md, etc.        ← alpha's actual codebase (untouched by paircode)

  .paircode/                           ← EVERYTHING paircode-related, hidden
    JOURNEY.md                         ← fleet log: active focus, roster, focus transitions
    peers.yaml                         ← single registry file declaring all peers + their configs

    peers/
      peer-a-codex/                    ← peer-a's working dir
        profile.md                     ← handshake result, capabilities, quota
        src/, tests/, ...              ← peer-a's cold code (full-fork mode only)
      peer-b-gemini/                   ← opinion-only peer
        profile.md                     ← handshake result
      peer-c-ollama/
        profile.md
        src/, tests/, ...              ← peer-c's cold code (full-fork)

    focus-01-ml-engine/
      FOCUS.md                         ← this focus's prompt, roster override, gate config
      research/
        alpha-v1.md ... alpha-vN.md
        peer-a-v1.md ... peer-a-vN.md
        peer-b-v1.md ... peer-b-vN.md
        reviews/
          round-01-peer-a-critiques-alpha.md
          round-01-peer-b-critiques-alpha.md
          round-02-...
        alpha-FINAL.md                 ← flat, not in a FINAL/ subfolder
        peer-a-FINAL.md
        peer-b-FINAL.md
      plan/
        (same shape: vN + reviews + FINAL per peer)
      execute/
        iter-001.md                    ← what happened round 1 (review summaries, fixes landed)
        iter-002.md
        ...
        iter-031.md
        HUMAN-GATE-resting-spot.md     ← gate marker when captain paused
        alpha-FINAL.md                 ← executive summary of this focus's execute stage
        peer-a-FINAL.md

    focus-02-clinical-data/
      FOCUS.md
      research/ ...                    ← new `.md` artifacts; alpha's src/ and peer-a's .paircode/peers/peer-a-codex/src/ keep evolving in-place
      plan/ ...
      execute/
        iter-001.md                    ← counter resets per focus
        ...
```

### Key structural principles

1. **Alpha's code NEVER moves into `.paircode/`.** Alpha = the project, project root is sacred.
2. **Full-fork peers' code lives inside `.paircode/peers/peer-N-{cli}/`** (visible ONLY when you `cd .paircode/`).
3. **Codebases persist across focuses.** Focus-02 doesn't clone focus-01's code — it continues from where focus-01 left alpha's src/ and peer-a's fork.
4. **Each focus contains only `.md` orchestration artifacts** — research/plan/execute stages produce text files, not code.
5. **FINAL files are flat**, suffixed `-FINAL.md`, not in a subfolder.
6. **Iteration counter resets per focus.** `focus-01/execute/iter-031.md` then `focus-02/execute/iter-001.md`. JOURNEY.md aggregates cumulative stats.
7. **No bubble-up to project root.** FINAL `.md` files stay inside `.paircode/`. The captain is notified verbally by the team-lead agent (the orchestrating Claude), e.g., *"FINAL for focus-02/plan completed at `.paircode/focus-02-*/plan/alpha-FINAL.md`, it says: …"* If later we want FINALs at project root, that's an additive choice, not a default.

---

## Naming — locked

| Concept | Name | Why |
|---|---|---|
| Framework / pypi package | `paircode` | Available on pypi; captures collaboration framing; works for all three peer modes |
| Slash command / CLI | `paircode` (and `/paircode` as Claude Code slash command) | Matches pypi name |
| Hidden orchestration folder | `.paircode/` | Dotted/hidden, matches `.git/`, `.venv/`, `.claude/` precedent |
| Primary developer's identity | **alpha** (implicit — is the project itself) | No subfolder; alpha = project root |
| Additional LLMs | **peer-a, peer-b, peer-c, ...** | Star topology spokes; named by order, suffixed with CLI identity (e.g., `peer-a-codex`) |
| Goal / chapter | **focus** (numbered `focus-01-*`) | Captain's steerable unit; each has its own research/plan/execute cycle |
| Work phase inside a focus | **stage** (research / plan / execute) | Universal peer-review engine invoked at each |
| Overall project timeline | **journey** | "Software journey" — captain's language; JOURNEY.md is the top-level log |

---

## Human gate semantics

Gates are **optional per stage**. Two declaration mechanisms:

### In `FOCUS.md` (durable)
```yaml
human_gate:
  mode: auto            # or: manual_between_stages, manual_every_N_rounds, manual_always
  max_rounds: 20
  convergence: 3_rounds_no_new_findings
```

### In the invoking prompt (transient)
> `paircode stage research --autopilot "I'm heading to bed, iterate until convergence or 20 rounds, then stop and wait"`

**File beats prompt** on conflict (file is durable truth; prompt is a one-off override).

### Auto mode

When `mode: auto` is set, the engine runs until one of:
- `max_rounds` reached
- Convergence criterion met
- A peer goes persistently offline (quota exhausted multiple rounds)
- Human writes a `HUMAN-GATE-*.md` file into the stage dir (takes effect next round)

**The captain is the final steering wheel.** Auto mode is a *convenience* for overnight / away runs, not a replacement for captain judgment.

---

## Quota / rate-limit graceful degradation

Each peer in `peers.yaml` has:
```yaml
peers:
  - id: peer-a-codex
    cli: codex
    model: gpt-5-codex
    mode: full-fork
    priority: high
    daily_budget_usd: 20
  - id: peer-b-gemini
    cli: gemini
    model: gemini-2.5-flash
    mode: opinion-only
    priority: low
    daily_budget_requests: 1500   # free-tier daily cap
```

### Policy

- Peer hits quota → that peer **sits out the rest of today's rounds**, rejoins at next daily reset.
- Round proceeds without them — **never halt the fleet for one peer's budget**.
- The iter-NNN.md log records "peer-b-gemini unavailable this round (quota exhausted)".
- Captain can override per-focus via `peers.yaml`: downgrade a paid peer to opinion-only when saving budget, or upgrade free-tier peer to pair-code when captain pays up.

---

## Auto-detection handshake (first-run behavior)

`paircode handshake` (also invoked implicitly on first `paircode` in a fresh project):

1. Scan PATH: `claude`, `codex`, `gemini`, `ollama`, `aider`, etc.
2. Scan env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_HOST`, ...
3. Ping each with a cheap "say hi, what model are you?" probe. Write `profile.md` per peer.
4. Propose roster:
   > "Detected: Claude Opus 4.7 (primary, paid), Codex CLI ($20 tier), Gemini-flash (free, rate-limited), Ollama kimi-2.5 (local unlimited). Suggest: alpha = Claude Opus (you), peer-a = Codex (full-fork), peer-b = Ollama (full-fork, unlimited), peer-c = Gemini (opinion-only, free-tier). Edit `peers.yaml` or accept?"
5. Write `peers.yaml`, `JOURNEY.md`.

---

## Reporting back to captain — the no-bubble-up principle

When a stage or focus completes, **the team-lead agent (the orchestrating Claude) reports textually**, not by moving files to project root. Example:

> "focus-02 (claims-data expansion) plan stage complete after 7 rounds. FINALs written:
> - `.paircode/focus-02-claims-data/plan/alpha-FINAL.md` — alpha's synthesis, says: '...'
> - `.paircode/focus-02-claims-data/plan/peer-a-FINAL.md` — codex's position, flags tension on ...
> - `.paircode/focus-02-claims-data/plan/peer-b-FINAL.md` — gemini's opinion, concurs on ...
>
> Ready to advance to execute stage. Shall I proceed, or do you want to review FINALs first?"

The captain reads the text summary, opens any FINAL they want to inspect, and says go/pause/revise. The conversation is the notification channel.

---

## What's in step A (this diary) vs. what's in step B and C

### Step A — understand (complete as of this diary) ✓
- Meta-pattern recognized and named
- Three layers (Journey / Focus / Stage) defined
- Universal peer-review engine shape locked
- N-peer star topology with alpha = project
- Three peer modes specified (full-fork / pair-code / opinion-only)
- File-trace schema finalized
- Naming locked (`paircode`, `.paircode/`, `peer-a/b/c`, `alpha = project`)
- Human gate semantics defined
- Quota degradation policy defined
- Reporting-back via conversation, not file bubble-up

### Step B — plan (next)
- Schemas for: `JOURNEY.md`, `FOCUS.md`, `peers.yaml`, `profile.md`, review round `.md` files, iteration `.md` files, FINAL `.md` files
- Command lifecycle for: first-run bootstrap, handshake, focus open, stage run, status, install-claude, install-codex
- Convergence detection algorithm
- MCP / toolnudger self-registration design (maybe — undecided)
- Test strategy: what's integration-tested vs. unit-tested

### Step C — ship
- Implementation of the step-B plan
- Pypi release (paircode 0.1.0 → public pypi)
- Claude Code slash-command installer (`paircode install-claude`)
- Codex CLI peer-invocation adapter (`paircode install-codex`)
- Real end-to-end test: run paircode on a fresh project, go through research → plan → execute for one focus, verify file-traces land correctly

---

## Things deliberately out of scope for step A

- **Exact prompt templates** for research / plan / execute stages — these will be customizable per project via `FOCUS.md`, not baked into paircode.
- **How peer code gets git-tracked** — could be nested repo, subdir under main repo, or gitignored entirely; captain's call.
- **Ops concerns** — telemetry, error reporting, update mechanism, backward compatibility — all deferred.
- **Bubble-up of FINALs to project root** — explicitly deferred. Captain will tell us if they ever want it.
- **Visual/TUI interface** — CLI + file-traces is enough for v0; maybe `paircode status --rich` later.
- **Multi-project / workspace mode** — focus on single-project case first.

---

## One principle above all

**Files on disk, always.** Every LLM output, every review, every version, every iteration log — written to `.md` or `.yaml`, readable by any tool, survivable across sessions and LLM vendor outages. If an idea didn't land on disk, it didn't happen. This is the spine of the whole framework.

---

*End of diary 001. Step-A architecture complete and locked. Step-B planning begins on captain's command.*
