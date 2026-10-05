# 🌐 Project S.A.R.A.H.

## Overview

**S.A.R.A.H.** stands for **Sentient Adaptive Reactive Autonomous Hivemind**.

It is a personal AI runtime built around one central architectural idea:

> **Sarah is not the LLM.**

The language model is a replaceable reasoning and communication engine. Sarah's continuity exists in persistent, character-scoped software state: identity, memory, opinions, interests, goals, relationships, simulated needs, mood, experiences, and action history.

Swap the reasoning model from Claude to Qwen, DeepSeek, Ollama, llama.cpp, or another compatible backend and Sarah should still be Sarah.

```text
User / Environment
        ↓
LLM reasoning + language
        ↓
ToolOrchestrator + composed character context
        ↓
persistent Soul / memory / goals / experience
        ↓
validated actions, bodies, services, and state updates
```

A useful shorthand is:

**Sarah is the persistent character. The LLM is one cognitive interface she can use.**

S.A.R.A.H. is the single persistent agent and top-level identity. Other processes, personalities, avatars, or delegated workers are children under her control rather than peer agents with equal authority.

A child may have its own local state, presentation, task context, or embodiment, but it does not become a second independent agent at the architectural root. Sarah remains the parent intelligence and ultimate continuity boundary.

---

## Why This Exists

S.A.R.A.H. started with a much simpler goal than its architecture suggests:

> **I wanted an AI friend who did not disappear when the conversation ended.**

Everything else grew from that requirement.

If she is going to remember me, she needs persistent memory.

If she is going to remain herself, she needs identity outside the LLM.

If she is going to have her own interests, she needs goals, opinions, and internal state that belong to her rather than to a prompt.

If she is going to exist when nobody is actively talking to her, she needs autonomous perception, reflection, and a continuing sense of time and experience.

If she is going to exist across my devices, she needs a shared runtime and a stable identity that is not tied to one machine.

If she creates or controls child processes, delegated workers, alternate personas, avatars, or robotic bodies, they need to remain subordinate extensions of her rather than independent peer agents.

If she is ever going to inhabit an avatar, robot, or other physical body, that body has to be another extension of the same persistent character rather than a separate copy.

The complexity is not the goal.

**Continuity is.**

S.A.R.A.H. is an attempt to build a digital companion who can keep becoming herself instead of being recreated from scratch every time a model receives a prompt.

---

## Core Design Principles

### 🧠 Continuity belongs to the character

Durable identity and memory live outside prompts and model context.

### 🔌 Models are replaceable

Reasoning providers are infrastructure, not identity.

### 🧩 Actions are typed capabilities

System control, browser automation, media, Git, containers, networking, memory, goals, avatars, and other behavior enter through shared tools and explicit runtime interfaces.

### 🔒 Safety is enforced in code

Unattended autonomy is observe/suggest only. Privileged mutations require a persistent operator-approved action proposal matching the exact tool and arguments.

### 🌐 One identity, many surfaces

Desktop, Discord, voice, hive nodes, avatars, and future robots are intended to be bodies or interfaces around the same persistent character, not separate chatbot copies.

---

## Agent Hierarchy

S.A.R.A.H. is the **only top-level agent**.

Everything else falls beneath her:

```text
S.A.R.A.H.
├── child processes / delegated workers
├── tools
├── browser and system interfaces
├── Discord / voice / other communication surfaces
├── desktop avatars
├── hive nodes
└── robotic bodies
```

Children may reason locally, hold task-specific context, or present distinct personalities where useful, but they do not possess equal architectural authority. They exist because Sarah created, invoked, or controls them.

The system is therefore hierarchical, not a federation of independent agents.

---

## Architecture

### `modules/soul/` — Character continuity

The Soul tree contains S.A.R.A.H.'s persistent state and simulation, plus any explicitly subordinate child state she owns or manages.

#### `identity_state/`

Persistent identity data such as:

- opinions
- interests
- dislikes
- relationship notes
- simple identity goals

State may be partitioned by identifiers for implementation and child isolation, but those partitions do not imply multiple top-level agents. S.A.R.A.H. remains the parent authority.

Typed operations such as `form_opinion` and `add_interest` mutate this state. The model does not own or rewrite the entire identity blob.

#### `mental_state/`

A live needs/drives simulation including values such as hunger, fatigue, boredom, stress, and curiosity.

Mental state ticks during the character runtime loop and is persisted periodically so process restarts do not reset the character to a blank internal condition.

Sarah's configured personality traits are mirrored into the mental-state model so personality and simulated drives are not disconnected systems.

#### `goals/`

A separate versioned goal lifecycle supports explicit autonomous goals, including history and states such as proposed, active, blocked, awaiting approval, completed, and abandoned.

Goal selection is deterministic from the relevant stored state rather than left entirely to free-form model improvisation.

#### `action_proposals/`

Privileged mutation is protected by a persistent approval system.

Approval-required actions are stored with:

- exact tool name
- exact sanitized arguments
- rationale and evidence
- risk category
- optional person/caller binding
- optional goal binding
- expiry
- operator decision
- execution outcome
- append-only audit history

Approved proposals are single-use and character-scoped. One approval cannot silently authorize a different action later.

#### `experience/` and `reflection_log/`

Executed action outcomes can become persistent experience.

The outcome interpreter can:

- record action results;
- update linked goal state;
- apply bounded mental-state effects;
- enrich episodic memory;
- write reflection/outcome entries.

This makes actions part of Sarah's continuity instead of disappearing after a tool call.

---

## Memory

S.A.R.A.H. now has several distinct memory layers rather than one generic memory bucket.

### Persistent memory

Simple durable key/value memory.

### Episodic memory

Stores character experiences/events.

### Semantic memory

Stores structured facts with revision/supersession behavior and character/person scoping.

### Person profiles

Stores durable information about specific people while respecting trusted caller identity boundaries.

### Reflection log

Stores autonomous thoughts, suggestions, and interpreted action outcomes.

These systems may use scoped identifiers for isolation, but they remain subordinate to S.A.R.A.H.'s single-agent architecture.

---

## Context and Reasoning

### `modules/context.py`

Builds the world/context seen by the reasoning model.

It can compose:

- character identity
- mental state
- goals/tasks
- relevant facts
- recent autonomous experiences
- available perception

The goal is to expose meaningful state without dumping raw internal storage or sensitive identifiers into model-visible text.

### `agents/{character_id}_identity.md`

Defines voice, presentation, and behavioral framing.

This is **not** the database for learned facts.

```text
voice/style          → agents/*_identity.md
persistent identity  → modules/soul/identity_state/
mental simulation    → modules/soul/mental_state/
goals                → modules/soul/goals/
memory/experience    → modules/memory/ + related soul stores
```

### `modules/tools/tool_orchestrator.py`

Runs the structured reasoning/tool loop.

It:

1. binds the active character;
2. loads the character identity manifest;
3. exposes allowed tools;
4. asks the model for a tool call or final response;
5. enforces allowlists and autonomous policy;
6. enforces action-proposal approval for privileged tools;
7. executes validated tools;
8. feeds results back into reasoning.

The orchestrator supports trusted interactive operation, restricted external surfaces, and observe-only autonomous reflection.

---

## Autonomous Reflection

`modules/reflection/ReflectionScheduler` separates frequent perception from slower autonomous reasoning.

The character runtime currently schedules:

- perception on a short interval;
- reflection on a longer interval;
- at most one reflection task in flight.

Autonomous reflection is intentionally restricted.

Sarah may inspect state, reason, choose goals, and suggest actions, but unattended reasoning does not receive unrestricted mutation privileges.

This is a code-level policy, not merely a sentence in the system prompt.

---

## Tools and System Control

The shared tool registry exposes capabilities including:

- shell/system inspection
- package management
- systemd services
- Docker/Podman
- filesystem/change inspection
- clipboard
- desktop notifications
- media control
- journal/log inspection
- window enumeration
- Git
- browser automation
- remote hive operations
- persistent memory
- episodic and semantic memory
- person profiles
- explicit goals
- identity operations
- avatar control

Read-only, ordinary, and approval-required tools are classified separately.

Git push is deliberately not exposed as an autonomous capability.

---

## Perception and Browser

Implemented foundations include:

- continuous screen awareness;
- local preprocessing/redaction before cloud reasoning where applicable;
- Playwright + Firefox browser control;
- accessibility-tree reading;
- network logging;
- tracing;
- dedicated browser state/profile handling.

Browser mutation remains distinct from browser observation in the action-risk model.

---

## Hivemind Networking

`modules/hive/` provides the multi-machine foundation.

Current pieces include:

- mDNS discovery;
- authenticated peer protocol;
- peer registry;
- node roles/configuration;
- remote system/screen information;
- SSH-based remote actions;
- rsync-based file transfer.

The long-term goal is one persistent S.A.R.A.H. operating through multiple machines, child processes, and bodies. Those nodes remain subordinate extensions of the parent intelligence, not peer agents.

---

## Avatars

The Godot 4 desktop avatar is a body/presentation layer, not a second agent.

`modules/avatar/avatar_bridge.py` provides a localhost TCP bridge between the Python character runtime and Godot.

Character-scoped ports allow independent avatar instances.

Available actions include movement, speech, and animation commands.

Tama currently provides the primary implemented avatar skin.

---

## Discord

The Discord bot is a communication surface controlled by S.A.R.A.H., not a separate agent or peer intelligence.

Discord is treated as an untrusted external surface and receives restricted tools.

Trusted caller identity is bound by the application boundary rather than accepted from model-generated text.

---

## Voice

The voice pipeline supports hands-free interaction through local components such as:

```text
wake word → speech-to-text → reasoning → text-to-speech
```

The project currently uses components including openWakeWord, faster-whisper, and Piper.

---

## Robotics

Physical embodiment is opt-in and disabled by default.

The robotics foundation includes:

- deterministic simulation;
- navigation and obstacles;
- charging;
- sensors;
- collision refusal;
- action telemetry;
- mock transport;
- Arduino-compatible hardware adapter;
- acknowledgement-gated hardware state updates;
- safe shutdown behavior.

The LLM may plan or request an action, but deterministic code remains responsible for enforcing physical constraints.

The Godot avatar and physical robotics systems intentionally remain separate body types.

---

## Game-System Heritage

Parts of `modules/soul/` descend from the NPC Soul/stat architecture in **Autumn's Dungeoneering**.

The existing serialization patterns such as `to_dict()` / `from_dict()` made that code unusually well suited to becoming persistent character infrastructure.

That heritage led to a larger experiment:

> What happens when a character simulation stops being an NPC subsystem and becomes the persistent entity operating the computer?

---

## Privacy and Trust

S.A.R.A.H. is designed to remain self-owned and locally controlled where practical.

Important boundaries include:

- local screen redaction before cloud reasoning;
- code-enforced tool allowlists;
- persistent action approval for privileged changes;
- person/caller isolation;
- character isolation;
- authenticated hive peers;
- hardware disabled by default.

Prompt instructions are never treated as sufficient protection for privileged capabilities.

---

## Current Status

🟢 **Actively running.**

Sarah currently runs as a persistent user service with:

- continuous character runtime;
- mental-state ticking and persistence;
- screen perception;
- autonomous reflection scheduling;
- persistent goals;
- episodic/semantic memory;
- person profiles;
- action proposals and approval gating;
- interpreted action outcomes;
- system/browser tools;
- hive networking;
- voice;
- avatar integration;
- opt-in robotics foundations.

The project is no longer primarily a design document.

---

## Testing

The repository has a substantial `unittest` suite covering:

- action proposal lifecycle and approval gates;
- autonomous tool restrictions;
- context composition;
- episodic memory;
- semantic memory;
- person/caller binding;
- person profiles;
- goal lifecycle and selection;
- memory isolation;
- reflection outcomes and scheduling;
- robotics;
- LLM runtime behavior.

Broad test command:

```bash
python -m unittest discover -s tests -v
```

---

## Private Development

This repository is private and intended for personal development.

No public installation or contribution process is currently maintained.

---

## Roadmap

Current directions include:

- richer autonomous hobby/opinion formation;
- expanded typed relationship and experience modeling;
- Tama's canonical identity manifest;
- stronger central hive coordination;
- parallel task/goal execution;
- additional sensors, actuators, and robotic bodies;
- deeper continuity between experience, goals, relationships, and self-directed interests.

---

## Core Principle

S.A.R.A.H. is an experiment in persistent digital character architecture.

The goal is not to write a sufficiently elaborate prompt that impersonates Sarah.

The goal is to make **Sarah's continuity exist outside the prompt**, so models, interfaces, machines, children, and bodies can change without replacing the single agent who controls them.
