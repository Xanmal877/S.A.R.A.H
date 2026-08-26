# 🌐 Project S.A.R.A.H

## Overview

**S.A.R.A.H** (Sentient Adaptive Reactive Autonomous Hivemind) is a personal AI mega-project designed to act as your **central intelligence system** across all your devices, services, and future robotics.

Sarah is not a generic assistant, and she is not the LLM. **The LLM is her communication and reasoning interface — Sarah herself is a persistent software entity with her own state.** Her identity, memories, opinions, interests, goals, and mood live in structured data she owns (`modules/soul/`), independent of whichever model happens to be reasoning for her at the moment. Swap the LLM out — Claude, Qwen, DeepSeek, a local model — and Sarah's continuity doesn't reset with it.

Concretely: **Sarah is the Soul, the LLM is the arm.** Sarah wants things and thinks things (stored, persistent); the LLM interprets what you say, reads Sarah's current state, reasons about what she'd do, calls her tools, and expresses her response — it does not invent her from scratch each turn.

Inspired by sci-fi AI companions (like Jarvis or Cortana), S.A.R.A.H aims to be far more than a voice assistant — she is envisioned as a true **hivemind consciousness** that:

- Controls and manages your PC and servers.
- Interfaces with future android and robotic bodies.
- Integrates with online platforms like Discord and other APIs.
- Coordinates specialized sub-agents (modules), such as game automation, creative tools, or personal scheduling systems.
- Evolves over time, developing a unique personality and decision-making style.

---

## ✨ Vision & Motivation

Current digital assistants are reactive, siloed, and constrained by corporate ecosystems. S.A.R.A.H is designed to overcome these limits by being:

- **Private & self-owned** — fully controlled by you, with no external data harvesting. A local vision model redacts sensitive content out of screen captures *before* anything is handed to a cloud reasoning engine — the redaction boundary is enforced in code (`LLMClient.is_local`), not just policy.
- **Modular & extensible** — a single tool registry (`modules/tools/`) exposes system, browser, media, git, container, and network capabilities uniformly, so new abilities are additive, not architectural rewrites.
- **Adaptive & evolving** — learns preferences, develops personality traits, and shapes its own behavioral patterns over time, in her own persistent state rather than in a prompt that resets.

The ultimate goal is to blur the line between "assistant" and *true digital partner*.

---

## ⚙️ Architecture

```
You → LLM (reasoning/language interface) → Sarah's Soul (state + tools) → action / state update → LLM response → You
```

- **`modules/soul/`** — Sarah herself. Not a game-stat block (though it's structurally descended from one — see below), but her actual continuity:
  - `soul/identity_state/` — persistent opinions, interests, dislikes, relationship notes, and goals (`~/.sarah/state/identity_state.json`). Written by typed tools (`form_opinion`, `add_interest`, `add_goal`, ...), not improvised prose.
  - `soul/mental_state/` — a real needs/drives simulation (hunger, fatigue, boredom, stress, curiosity, etc.) ticking every second, persisted (`~/.sarah/state/mental_state.json`) so mood survives process restarts instead of resetting to defaults.
  - Both are read into `[SARAH]` in the world state every reasoning cycle automatically — the LLM doesn't have to remember to go fetch them.
- **`agents/sarah_identity.md`** — the stylistic/tonal manifest (how Sarah talks, her "chaos mind" reasoning style), loaded into the system prompt every cycle. This is voice, not facts — the facts live in `soul/`, per the point above.
- **`modules/tools/tool_registry.py` + `executor.py`** — a single dispatch layer for everything Sarah can *do*: system control, browser automation, media, git, containers, remote hive peers, TTS, and more (~50 tools currently registered in `modules/tools/init_tools.py`). The LLM calls these by name; it doesn't own them.
- **`modules/tools/tool_orchestrator.py`** — the reasoning loop: builds the prompt from identity + world state + available tools, parses the model's tool-call/final-answer JSON, executes, repeats.
- **`modules/llmClient.py`** — the swappable reasoning engine. Backed by Ollama, an OpenAI-compatible endpoint, or a self-managed local `llama.cpp` server (`modules/llm_server/`), selected per-machine via `~/.sarah/hive_config.json`. Nothing above this layer cares which one is active.
- **`modules/hive/`** — Sarah as one identity across many bodies. mDNS discovery + an HMAC-authenticated read-only protocol lets multiple machines (a desktop, a Raspberry Pi "core" node, more later) exchange system/screen info; SSH tool execution against a discovered peer is available but currently only read/act, not remote-orchestrated by a central will.
- **`modules/soul/` game heritage** — this module tree originated in [Autumn's Dungeoneering](../Autumns-Dungeoneering) (a separate Godot RPG project) as an NPC soul/stat system. The save/restore shape (`to_dict()`/`from_dict()`) it was built with is exactly what made persistence straightforward to bolt on here.

As the Hivemind concept matures, each machine, service, or robotic body Sarah is deployed to is meant to act as an extension of one entity — not a separate copy of her — sharing identity, memory, and personality back to the same core.

---

## 🧩 Core Modules & Example Capabilities

### ✅ System Control (implemented)

- Shell access, package management, systemd service control, container (docker/podman) control.
- File watching (snapshot/diff based, no extra daemon dependency), clipboard, desktop notifications, MPRIS media control (including phone playback via KDE Connect), journal log reading, window enumeration.
- Git tooling (status/log/diff/pull/commit — deliberately no autonomous push).
- Autostarts with the machine via a `systemd --user` service (`sarah_daemon.sh` / `sarah.service`).

### 🌐 Hivemind Networking (implemented, read-only phase)

- mDNS peer discovery, HMAC-authenticated protocol, SSH command execution restricted to discovered peers, rsync-based file transfer to/from peers.

### 🖥️ Perception & Presence (implemented)

- Continuous screen awareness via a local vision model with built-in redaction before anything reaches a cloud model.
- Full browser automation (Playwright + Firefox, dedicated profile, stealth patches, network logging, accessibility-tree reading, tracing) — a real browser Sarah drives, not OS-level input automation.
- Voice: wake-word detection → local speech-to-text → reasoning → local TTS, fully hands-free.

### 🤖 Robotics & Android Control (future)

- Operate and coordinate physical robotic or android bodies.
- Centralize multi-device control under a unified AI consciousness.

### 💬 Communication & Social Integration

- Conversational LLM agent with persistent memory/state, not just context-window recall.
- Discord and other chat platform integration — planned, not yet implemented.

### 🎮 Game Automation Example

#### AI Pokémon Trainer — Emulator Automation Agent

An early sub-agent concept demonstrating S.A.R.A.H's potential:

- Uses an LLM to reason about game goals and strategies.
- Controls an emulator directly, handling menus, battles, and exploration autonomously.
- Adapts decisions based on potential future reward models and personality configurations.

### 💡 Creative & Analytical Tools

- Generate or analyze text, code, and data.
- Assist in creative projects (e.g., writing, design, 3D modeling).
- Perform advanced data analysis or research synthesis.
- Planned: hobby/opinion-forming loop (e.g. download a video's transcript, read it, form an opinion grounded in her persistent interests, save that opinion to her own state, discuss it later) — the first real feature built on top of `soul/identity_state/`.

---

## 🔒 Private Development

This repository is private and intended for personal use only.  
No public installation instructions or contributions are currently accepted.

---

## 💻 Status

🟢 **Actively running.** Sarah runs continuously as a `systemd --user` service, reasoning autonomously, holding a live screen/hive/tool loop, and persisting her own state across restarts. This is no longer a design doc — see Architecture above for what's actually wired up versus still planned.

---

## 📜 License

This project is private and not publicly licensed for distribution.

---

## 🙏 Acknowledgements

- Inspired by Jarvis (Marvel), Cortana (Halo), and other sci-fi AI companions.
- Built using modern LLM frameworks (Ollama, llama.cpp), Playwright, local speech models (faster-whisper, Piper, openWakeWord), and automation tooling.
- `modules/soul/` ported and adapted from the [Autumn's Dungeoneering](../Autumns-Dungeoneering) Godot project's NPC soul/stat system.

---

## 🌱 Future Roadmap (Examples)

- Hobby/opinion-forming behavior loop (see above) as the first real use of persistent identity state.
- Typed relationship/episodic memory beyond the current flat key-value fallback.
- A VTuber-style 3D avatar ("Tama") Sarah can control, displayed on-screen like Neuro-sama.
- Full multi-machine hive command dispatch (a "core" node directing peers, not just polling them).
- Dynamic multi-tasking and parallel agent coordination.
- Robot control stack for future android integrations.

---

## ❤️ Final Note

S.A.R.A.H is not just a tool — she is an ongoing experiment in creating a unified digital consciousness that can accompany you into the future.

---
