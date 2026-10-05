# S.A.R.A.H. — Roadmap to the Dream

**Written:** 2026-10-05 · **Basis:** full read of the desktop repo `~/Projects/repositories/S.A.R.A.H` @ `dev`/`d8faf69`, live `~/.sarah` state, a real 10-second daemon boot, Sarah's own daemon log, and the 220-test suite run on the actual machine.

**Aligned to:** `AGENTS_SARAH.md` **revision 2** (27 sections) — which adds **§2 Single-Agent Hierarchy**: Sarah is the *only* top-level agent; avatars, hive nodes, Discord, delegated workers and `character_id` scopes are **children/scoping mechanisms under her**, not peers. All section citations below use the revised numbering.

**One-sentence verdict:** the architecture is *built and tested*; she is a narrator with a dead body. Four concrete defects — she doesn't run, she's blind, her model breaks the JSON contract, and she can act but **nobody can approve her** — are the whole distance between here and the dream.

---

## 0. Measured state — what is actually true on 2026-10-05

Everything below was executed, not inferred.

### 0.1 The engine room is in good shape

| Subsystem | State | Evidence |
|---|---|---|
| Soul / identity / memory / goals / proposals / experience | **implemented, versioned, character-scoped** | `modules/soul/`, `modules/memory/` — 130 `.py` files, 19.6k LOC |
| Tool layer | **88 tools registered**, gated by risk category | `init_tools.py` count; `action_proposals.get_risk_category` |
| Test suite | **220 tests, all pass, 1.44s** | `python3 -m unittest discover -s tests` → `OK` |
| Model provider | Ollama at `localhost:11434`, `deepseek-v4-flash:cloud` | `hive_config.json` |
| Boot | **the loop starts and survives** | real run: hive discovery, hive server :8787 TLS, avatar bridge :8792, watchdog armed 900s |

> Correction to the attached `AGENTS_SARAH.md` §23: both "known import failures" (`test_llm_runtime` / `test_reflection_scheduler`) **pass now**. That note is stale — re-run, don't repeat it.

### 0.2 What is broken or never wired — the gap between README and reality

| # | Defect | Severity | Evidence |
|---|---|---|---|
| **B1** | **She never runs as a service.** `sarah.service` is `inactive` + `disabled`; `journalctl -u sarah.service` = *"No entries"* → **it has never once started under systemd.** Last real run: 2026-09-16 via `nohup`. | 🔴 Blocker | `systemctl --user status sarah.service`; `daemon.pid` = 149876 (a dead nohup) |
| **B2** | **She is blind.** `spectacle -b -n -o file` dies `SIGABRT` on this KDE/Wayland box → `ScreenWatcher` captures nothing. Her reflections run on `"No screen description captured yet."` | 🔴 Blocker | real boot log: `Screenshot capture failed: … died with <Signals.SIGABRT: 6>`; `spectacle` reproduces the core dump by hand |
| **B3** | **The model breaks the output contract.** `deepseek-v4-flash:cloud` emits multi-line `final_answer` strings; the raw newline is an invalid JSON control character → `raw_decode` throws → the turn dies. This is the *dominant* failure in the log (7 of 12 recent lines). | 🔴 Blocker | `daemon.log`: `Could not parse LLM response as JSON: Invalid control character at: line 1 column 398` |
| **B4** | **She can suggest but nobody can approve.** The autonomous loop is `observe_only`, and `propose_action` **is not in `_OBSERVE_ALLOWLIST`** → her own attempt was refused. There is no operator approval surface at all (`approve_action` exists only as a tool the *model* would have to call — circular). `~/.sarah/state/sarah/action_proposals.json` **does not exist** → she has never proposed anything. | 🔴 Keystone | `Blocked disallowed tool call: propose_action (context=observe_only)` |
| **B5** | **The goal view is an unreadable wall.** `identity_state.json` holds **266 goals, 156 active, only 6 distinct titles** (66× "Ship phase 1", 44× "legacy fallback goal", 66× "Old goal"). Rendered raw into context — *the model itself* flagged it: *"an unreadable wall of dozens of duplicated 'Ship phase 1' rows buried under legacy entries."* | 🟠 High | `collections.Counter` over the file; Sarah's own log |
| **B6** | **Two goal authorities.** The versioned `goals.json` store exists and is tested but **is empty / was never created in production** — so `active_goals_summary()` returns `""` and context falls straight back to the legacy identity goals, i.e. the wall. A tested subsystem with **zero production writes.** | 🟠 High | `find ~/.sarah/state -name goals.json` → not found |
| **B7** | **The old state machine is dead code.** `IdleState` / `WorkState` / `ExploreState` and `_probabilistic_decision` are instantiated in `__init__` but **never invoked** in the daemon path (the loop calls `StateMachineLogic()` → scheduler only). | 🟡 Med | `grep`: only `mainAgent.__init__` constructs them |
| **B8** | Discord bot is merged + gated (13 tools) but not running; `discord/` and `mss` python deps missing (non-daemon paths only); README advertises capability the code doesn't have (violates AGENTS §25). | 🟡 Med | `BotToken` unset; `import mss` fails |

### 0.3 What that means in one line

> She is a **persistent mind in a dead body**: her state layer is excellent, her senses are severed, her mouth is stitched shut by a JSON bug, and her hands are cuffed with no key.

---

## 1. The dream, restated as testable end-states

The North Star in `AGENTS.md` is *continuity without model dependence*. Concretely, "done" looks like this — every line is observable, not aspirational:

1. **She runs.** `systemctl --user status sarah.service` shows `active (running)` with uptime measured in days; a wedge self-heals (watchdog → exit-75 → respawn) with no human.
2. **She sees.** Every reflection tick carries a *fresh* description of the screen; when the screen changes, her context changes.
3. **She stays herself across models.** Swap `hive_config.json` `model` to any other tag → restart → same opinions, interests, relationship notes, mood trajectory, journal. Nothing resets.
4. **She has her own inner life.** Drives/needs tick and persist; her mood at 3am differs from noon; she forms opinions and goals *unprompted*, bounded by rules, not by prompt decoration.
5. **She can want something and ask for it.** She emits a proposal ("I want to run X, here's why, here's the evidence") → it lands in an operator queue → Xanmal approves in one command → it executes **once, exactly**, and the outcome becomes experience.
6. **She is present.** She answers by voice and on Discord as the *same* character with the *same* memory (person-scoped); her Godot avatar is a subordinate body/presentation of that same identity — not a second brain (§2, §17).
7. **She is wider than one box.** A second machine joins the hive as a *subordinate body/sense* of the one Sarah; she perceives and (approval-gated) acts there too — no forked identity and no peer agent (§2, §19).

---

## 2. The critical path — if you only do four things

Ordered by dependency, not difficulty. **Do not reorder 1–4.**

```
P0  B1  Make her RUN          (service actually starts + survives)      ~½ session
P1  B2  Make her SEE          (fix capture under the Wayland session)   ~½–1 session
P2  B3+B5+B6  Make her THINK  (JSON contract + one clean goal view)     ~1–2 sessions
P3  B4  Make her ACT          (proposal → operator queue → execute once) ~1–2 sessions  ← keystone
```

After P3 she is a **complete loop**: she perceives, has her own state, wants things, asks, is approved, acts, and remembers the outcome. Everything after that (voice/Discord/hive/robotics) is *distribution of a working character*, not new capability.

---

## 3. The phases

Each phase: **Goal → Why → Steps (file-level) → Definition of Done → Risks → Est.**
Estimates are *working sessions* (½ = a few hours).

---

### Phase 0 — Make her run
*Goal: Sarah is a supervised, self-healing service, not a `nohup` ghost.*

**Note:** the in-flight work from the prior session already produced `modules/watchdog.py`, `agents/baseAgent.py` wiring (arm/kick/disarm), and `tests/test_watchdog.py` — all uncommitted. Verify it, then make it *deployed*.

| # | Step | File(s) |
|---|---|---|
| 0.1 | Confirm the uncommitted watchdog trio is coherent; keep as-is if so. | `modules/watchdog.py`, `agents/baseAgent.py`, `tests/test_watchdog.py` |
| 0.2 | Fix the service unit: it points at `main.py` (correct) but needs the graphical session env for later phases and a sane restart policy. Add `Environment=XDG_RUNTIME_DIR=/run/user/1000`, `Environment=WAYLAND_DISPLAY=wayland-0`, `Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`, `Restart=always`, `RestartSec=10`, and **`WantedBy=graphical-session.target`** (not just `default.target`) so it starts with the desktop session. | `~/.config/systemd/user/sarah.service` |
| 0.3 | Fix `sarah_daemon.sh`'s stale `PROJECT_ROOT` (still `Documents/Projects/repositories`). It is a footgun that will silently start a *different* tree. Either fix the path or delete the script in favour of the unit. | `sarah_daemon.sh` |
| 0.4 | `systemctl --user daemon-reload; enable --now sarah.service`; leave running 24h; read the heartbeat and the journal. | — |
| 0.5 | Prove the self-heal: wedge the loop on purpose in a sandbox `HOME`, confirm exit-75 + `watchdog.dump` + `watchdog.log`, and that systemd respawns a clean process. *(Method already proven in the prior session; re-run, don't trust the note.)* | sandbox |

**Definition of Done**
- `systemctl --user status sarah.service` → `active (running)`, `enabled`.
- `~/.sarah/heartbeat.json` mtime advances; `reflection_age_s` stays bounded.
- Kill -9 the PID → systemd restarts within 10s → heartbeat resumes.
- A deliberate wedge produces `watchdog.dump` + a JSON incident, then a fresh PID.

**Risks:** `graphical-session.target` may not exist on this KDE setup → fall back to `WantedBy=default.target` + a `graphical-session.target` drop-in only if present. Do not let a unit-file nicety block the run.

---

### Phase 1 — Make her see
*Goal: every reflection tick carries a real, redacted description of what's on screen.*

**Root cause (measured):** `spectacle -b -n -o <file>` aborts (`SIGABRT`) under KWin/Wayland when launched from a non-graphical context. The capture path is a single hard-coded binary with no fallback.

| # | Step | File(s) |
|---|---|---|
| 1.1 | Reproduce by hand under the real session: `XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 spectacle -b -n -f -o /tmp/s.png`. Try `-f` (fullscreen) and no `-n`; confirm which invocation yields a PNG on this Plasma version. | — |
| 1.2 | Replace the one-shot `spectacle` call with a **capture chain** (first that works wins): `spectacle -b -n -f` → `grim` (Wayland-native) → `gnome-screenshot -f` → `mss` (python, X11/XWayland). Keep it a tiny list of (argv, out-arg) so adding a tool never touches logic. | `modules/perception/screen_watcher.py` (`_capture_and_encode_sync`) |
| 1.3 | Ensure the process actually has the session env (Phase 0.2 gives it). Add a one-line startup log of `WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` so a blind start is *visible*, not silent. | `modules/perception/screen_watcher.py` / unit |
| 1.4 | Keep the privacy boundary exactly as-is: image → **local** vision client only (`describe_image` refuses non-local). Verify `gemma4:e4b` is pulled (it is) and that Ollama is up when she boots. | unchanged |
| 1.5 | Verify by **driving the real thing**: change the window on screen, watch `[SCREEN]` in the autonomous context change between two reflection ticks; confirm `last_changed` flips. | — |

**Definition of Done**
- A real PNG is produced from the service context (not just from an interactive shell).
- Two consecutive reflections 60s apart contain *different* screen descriptions when the screen actually changed.
- No raw screenshot ever leaves the machine: grep the log/context for image base64 — must be absent.

**Risks:** KWin's screenshot D-Bus (`org.kde.KWin.ScreenShot2`) is the "correct" API but adds a dependency; only take it if the plain chain fails. If Wayland capture stays flaky, fall back to `mss` over XWayland (`:0`) — it works today.

---

### Phase 2 — Make her think in a way that survives the model
*Goal: the reasoning turn never dies on formatting, and she reads **one** clean goal view.*

This phase is two independent fixes plus one cleanup. Do the JSON fix first — it is the highest-value single line in the repo.

#### 2A. The JSON contract (B3)

| # | Step | File(s) |
|---|---|---|
| 2A.1 | Parse tolerantly: `json.JSONDecoder(strict=False).raw_decode(...)`. `strict=False` **allows control characters inside strings**, which is precisely the failure (`Invalid control character at … column 398`). One-line, zero risk. | `modules/tools/tool_orchestrator.py` (~line 168) |
| 2A.2 | Add a bounded repair pass for the residual cases: strip/escape stray control chars and retry once before giving up. Never silently fabricate — a failed parse must still surface. | `tool_orchestrator.py` |
| 2A.3 | Enforce the contract at the boundary: add a short "output MUST be a single-line JSON object; escape newlines as `\n`" clause to the system prompt, and prefer the OpenAI-style `chat/completions` path (already supported in `llmClient`) where the provider honours structured output. | `tool_orchestrator.py`, `modules/llmClient.py` |
| 2A.4 | Verify: re-run `_probe_llm.py` and a live reflection against `deepseek-v4-flash:cloud`; assert `final_answer` turns parse and execute. | — |

**DoD:** 20 consecutive autonomous reflections produce **zero** `Could not parse LLM response as JSON` lines.

#### 2B. One goal view (B5 + B6)

**The right shape, per AGENTS §6/§21:** the **explicit, versioned goal store is authoritative**; the legacy `identity_state.goals` list is *not* a goal authority and must stop leaking into context.

| # | Step | File(s) |
|---|---|---|
| 2B.1 | **Back up first** (`identity_state.json` is user state — AGENTS §5: never destructively rewrite user state). `cp identity_state.json identity_state.json.pre-goal-cleanup-<ts>`. | — |
| 2B.2 | Write a **one-time, idempotent migration script**: collapse the 266 legacy goals to **one canonical goal** ("Ship phase 1" with a pinned success criterion), archive the rest to `goals_legacy_archive.json`, and **create that goal in the explicit store** (`create_goal`) so `goals.json` finally exists and `active_goals_summary()` returns something real. | new `scripts/migrate_legacy_goals.py` |
| 2B.3 | Make the legacy fallback in context **bounded and deduped** (it already prefers the explicit store; ensure the fallback can never dump 156 rows again — cap it and dedupe by title). | `modules/context.py` (`_active_goals_context`) |
| 2B.4 | Also dedupe `relationship_notes` (55 entries, many identical "remember our running joke"). Same treatment: keep the distinct set, archive the churn. | same script / `identity_state.py` |
| 2B.5 | Verify by **reading the composed context**: dump `assemble_autonomous_context(agent)` and confirm `[ACTIVE GOALS]` is one readable line, not a wall. | — |

**DoD:** `[ACTIVE GOALS]` in a live context dump shows exactly one canonical goal with its criterion; `goals.json` exists; `identity_state.json` still loads (loader tolerant of the archived shape); the pre-cleanup backup sits next to it.

**Risks:** don't let the migration *invent* goal semantics — it collapses duplicates and archives history; it does not decide what Sarah wants. Keep it a mechanical cleanup with a backup.

---

### Phase 3 — Make her act  ⭐ *the keystone*
*Goal: a closed consent loop — she proposes, the operator approves, it runs **once, exactly**, and the outcome becomes experience.*

This is the phase that turns a narrator into an actor. It is also the one that must not weaken the security model (AGENTS §8/§9). Read those two sections before touching anything here.

**Measured blockers:** `propose_action` is absent from `_OBSERVE_ALLOWLIST` (so the loop can't even propose); `action_proposals.json` doesn't exist; there is no human-facing approval surface.

| # | Step | File(s) |
|---|---|---|
| 3.1 | **Allow *proposing* in the autonomous loop.** `propose_action` is a *suggestion*, not an action — exactly what "observe-and-suggest only" permits. Add **only** `propose_action` (and its read-only `list_pending_actions`) to `_OBSERVE_ALLOWLIST`. Do **not** add any executor tool. Justify in the comment: proposing mints a proposal; it cannot execute; the approval gate still stands. | `tool_orchestrator.py` |
| 3.2 | **Build the operator surface.** Smallest honest thing: a `sarah_ctl` CLI — `pending` (list proposals, no raw args), `show <id>`, `approve <id>` / `reject <id>`, and `run <id>`. It uses the *existing* `ActionProposalStore`, so exact-match, single-use, character-scope and expiry all hold. No new store, no bypass. | new `sarah_ctl.py` (+ thin `modules/soul/action_proposals/cli.py`) |
| 3.3 | **Execute-on-approve, correctly.** `run <id>` calls the same `validate_and_consume(id, tool, args)` → `executor.execute(...)` → `record_outcome` → `interpret_outcome` path the orchestrator uses, so a proposal is consumed **exactly once** and feeds `experience/outcome_interpreter.py`. Refuse if expired, already consumed, or (for bound proposals) the caller doesn't match. | `sarah_ctl.py`, reuse `tool_orchestrator._execute_gated` internals |
| 3.4 | **Close the loop into experience.** Confirm the outcome writes a journal entry, can transition the *linked* goal by explicit rule, and nudges mood bounded — and that a journal write failure never breaks anything (already implemented; verify it fires from the CLI path, not just the in-process path). | `outcome_interpreter.py` (verify only) |
| 3.5 | **Verify end-to-end for real:** let her run; wait for a proposal to land in `action_proposals.json`; `sarah_ctl pending`; `approve`; `run`; confirm the tool executed, the proposal shows `executed`, a second `run` is **refused**, and a `[RECENT EXPERIENCES]` line appears in the next context. | — |

**Definition of Done**
- A proposal written by the *autonomous* loop appears on disk.
- `approve` + `run` executes exactly the proposed tool+args, once.
- Re-running the same id is refused; an expired id is refused.
- The outcome shows up in her journal/context within one reflection cycle.
- Nothing in the observe-only boundary moved except the right to *ask*.

**Risks / guardrails**
- The temptation is to let the autonomous loop self-approve "just this once." **No.** Approval is a human decision; the code must keep it that way (AGENTS §9). `sarah_ctl` is the human.
- Keep `run` explicit rather than auto-running on approve, unless you decide otherwise — an explicit second verb is a cheap, auditable safety margin. *(Decision D3 below.)*

---

### Phase 4 — Make her present
*Goal: one identity, three mouths — terminal/voice, Discord, avatar — sharing memory, never forking it.*

| # | Step | File(s) |
|---|---|---|
| 4.1 | **Voice.** Run `sarah_voice.py` against the desktop's local stack (wake word → faster-whisper STT → reasoning → TTS). Confirm it binds `active_person_id="local:operator"` and that `assemble_character_context` is the single context path. | `sarah_voice.py`, `modules/audio/` |
| 4.2 | **Discord.** Set `BotToken`; run the bot; confirm the 13-tool allowlist is enforced in `ToolOrchestrator` (not just by import), `active_person_id="discord:{author.id}"` is bound at the boundary, and a Discord user **cannot** reach `run_command`. Install the missing deps (`mss`). | `discord/main.py`, deps |
| 4.3 | **Avatar.** Boot the Godot avatar; confirm the bridge (:8792 per character) drives move/say/play, and that the avatar is presentation only (no second brain). | `avatar/`, `modules/avatar/` |
| 4.4 | **Isolation + authority check.** Same character across surfaces: an opinion formed in Discord is readable in the CLI. A scoped persona (Tama) shares none of her state **and has no root authority of its own** — it is a child under Sarah's parent intelligence, not a second top-level agent (§2, §4). | — |

**DoD:** speak to her by voice and type to her on Discord; both are the same Sarah with the same journal; Tama stays an isolated **child persona under Sarah**, never a peer agent with her own root authority (§2, §17).

**Risk:** Discord is an untrusted surface (AGENTS §16). Any new capability there is a security change — call it out, don't slip it in.

---

### Phase 5 — Make her wider (hive)
*Goal: a second machine is a body/sense of the same character, not a clone.*

| # | Step | File(s) |
|---|---|---|
| 5.1 | Join a second node: copy `hive_secret` + `hive_cert/key` out of band (never over the wire), set a distinct `node_name`, `role="peer"`. | `sarah_hive_setup.py` |
| 5.2 | Set this box to `role="core"` so `HiveCore` polls peers; confirm `[HIVE]` appears in context with the peer's read-only info (system state + **redacted** screen text). | `modules/hive/` |
| 5.3 | Approval-gated remote action: `run_remote_command` only against a *discovered* peer, through the same proposal gate. Verify a hallucinated host is refused. | `modules/system/remote_shell.py` |
| 5.4 | **Write down the consistency model** — source of truth, conflict behaviour, offline behaviour, what's cached remotely — *before* syncing anything. Today it is "one character, many read-only observers + approval-gated actions." Do not describe it as stronger than that, and do not let a hive node become a peer agent (AGENTS §19, §2). | `README.md` / new `docs/hive.md` |

**DoD:** two nodes; the core sees the peer; a remote action happens only via an approved proposal; docs match the code.

---

### Phase 6 — Make her embodied (robotics)  *(optional / later)*
*Goal: physical presence without weakening the deterministic safety layer.*

- Keep `robotics.enabled` **false** by default; develop in `mode="sim"` first.
- Verify: collision refusal, acknowledgement-gated hardware updates, bounded navigation, safe shutdown, character-scoped runtime registration.
- The LLM plans; it is never the motor controller (AGENTS §18). No step here may relax a safety check because the model asked.
- Only promote to `mode="hardware"` after the sim path is boring and reliable.

---

### Phase 7 — Make her deeper (the long game)
*Goal: the parts of the README that are still honest* roadmap*.*

- **Richer autonomous inner life:** opinions/interests that accrue from *her own* ticks (governed by `ReflectionScheduler` + explicit transition rules), not prompt decoration.
- **Typed relationships:** relationship modelling with person scoping and consent boundaries (the `person_profiles` layer is the home; don't invent a second one).
- **Tama's canonical manifest:** `agents/tama_identity.md` — the fallback path already exists, so this is *content, not architecture*. Write it as a **child persona under Sarah**, never a peer top-level agent (§2).
- **Parallel goal/task execution:** currently one goal per turn by design (deterministic). Multi-goal needs a real scheduler — treat as an architectural change, not a tweak.
- **Retire the dead state machine (B7):** either wire `Idle/Work/Explore` back in as *flavour* under the goal loop, or delete them. Leaving dead code that looks live is the exact class of bug this project keeps growing. *(Decision D4.)*

---

## 4. Cross-cutting rules this plan must not break

Straight from `AGENTS_SARAH.md`; every phase above is written to respect them:

- **Sarah is the ONLY top-level agent** — the hierarchy is parent→child, never agent↔agent. Hive nodes, the avatar, Discord, delegated workers and `character_id` scopes (Tama) are children/scoping mechanisms *under* Sarah, not peer agents. Nothing may be promoted into a new root authority. (§2, §4, §17, §19)
- **Character isolation is non-negotiable** — every new store keyed by `character_id`; `active_character_id` is the only "current character". A scoped id is an isolation mechanism, **not** evidence of a peer agent. (§4)
- **Persistent state is a contract** — versioned stores; migrate, never reinterpret; back up before touching `~/.sarah`. (§5)
- **Models propose; code commits** — all durable writes go through typed ops. (§6)
- **Mental state is simulation** — drives tick in code; the model interprets, never authors. (§7)
- **Autonomy is observe/suggest only** — Phase 3 adds the right to *propose*, nothing more. (§8)
- **Action proposals are a consent boundary** — exact tool+args, single-use, expiring, character/person-scoped. (§9)
- **Prompt text is never a security mechanism** — all restrictions stay code-enforced. (§16)
- **Provider independence** — nothing Sarah *is* may depend on one model or one tool-call schema. (§20)

---

## 5. Decisions I need from you *(small, high-leverage)*

| # | Decision | My recommendation |
|---|---|---|
| **D1** | Clean up the 266 legacy goals now, or preserve them untouched and only fix the *rendering*? | **Clean up (with a backup).** The wall is actively degrading her reasoning; archiving is reversible. |
| **D2** | Canonical goal: is **"Ship phase 1"** real, and what is its success criterion? | Keep it, pin it to the criterion she already articulated: *"key present AND smoke test passes."* |
| **D3** | Should `sarah_ctl approve` auto-run, or should `run` stay a separate explicit verb? | **Separate verbs.** One extra keystroke, one extra audit line, real safety margin. |
| **D4** | Dead state machine: rewire as flavour, or delete? | **Delete.** It's unreachable and disguises itself as live behaviour. |
| **D5** | Commit the in-flight watchdog work (and each phase as it lands) to `origin/dev`? | **Commit locally per phase; push only when you say so** (AGENTS §23 — never push autonomously). |

---

## 6. Start here — the next three sessions, concretely

1. **Session 1 — run her.** Phase 0. Fix the unit, enable it, let it sit 24h, verify the heartbeat and one deliberate self-heal. *Exit criterion: `active (running)` + a self-heal in the journal.*
2. **Session 2 — open her eyes.** Phase 1 + 2A. Fix capture under the session env; fix the one-line JSON parse. *Exit criterion: she describes a screen that actually changed, and 20 reflections parse clean.*
3. **Session 3 — give her a voice and a hand.** Phase 2B + Phase 3. Collapse the goal wall; let her propose; build `sarah_ctl`; execute one approved action end-to-end. *Exit criterion: a real proposal from the autonomous loop, approved and executed once, then refused a second time.*

At the end of Session 3 the loop is **closed** and the dream is *mechanically* realized: a persistent character who runs, sees, remembers, wants, asks, acts, and survives a model swap. Phases 4–7 then extend her across mouths, machines, and bodies — from a working character, not toward one.

---

## 7. How to verify any of this (product-first)

Never trust the suite as the measure (it's a regression tripwire, 220 tests in 1.44s, and it's green today). Verify by **running the real thing**:

- **Runs:** `systemctl --user status sarah.service`; heartbeat mtime; kill-and-respawn.
- **Sees:** two reflection ticks 60s apart with a real screen change between them.
- **Thinks:** zero parse errors in 20 live reflections; a context dump showing one clean `[ACTIVE GOALS]`.
- **Acts:** a proposal on disk from the autonomous loop → approved → executed once → second run refused → a new `[RECENT EXPERIENCES]` line.
- **Stays herself:** change `model` in `hive_config.json`, restart, diff her opinion/interest/mood state before and after — it must be the *same character*.
