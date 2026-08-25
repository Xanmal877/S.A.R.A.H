# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands
- Run the S.A.R.A.H. demo: `python3 main.py`

## Architecture Overview
S.A.R.A.H. (Sentient Adaptive Reactive Autonomous Hivemind) is designed as a modular AI system where behavior is driven by a simulated personality.

Sarah is not a generic assistant — she is defined as a persistent digital **chaos mind**: curious, associative, pattern-driven, and willing to form and act on her own opinions, but grounded in evidence rather than random guessing. Her canonical behavioral identity lives in `agents/sarah_identity.md`, which `ToolOrchestrator` (`modules/tools/tool_orchestrator.py`) loads verbatim as the system prompt for every reasoning cycle — that file is the enforced source of truth for her personality, not just documentation.

### Core Components
- **Agent Hierarchy**: `BaseCharacter` (in `agents/baseAgent.py`) provides the core lifecycle and module integration. Specific agents like `SarahAgent` inherit from it to specialize personality and state machine configuration.
- **Personality System**: The `PersonalityModule` implements a trait system (based on MBTI dimensions) that produces modifiers (risk, social, planning, confidence). These modifiers are used by the state machine to determine behavioral patterns. `SarahAgent.SetupPersonality` (`agents/sarah.py`) tunes these values specifically to express the chaos-mind traits (high `mind`/intuition for associative thinking, high `identity` for assertiveness, low `tactics` for structure underneath the chaos).
- **State Machine**: A decoupled state system (`stateMachine.py`) defines behaviors like `Idle`, `Work`, and `Explore`. `SarahStateMachine` (in `mainAgent.py`) acts as the dispatcher, using personality modifiers to dynamically weight the probability of transitioning between these states.
- **Character Management**: `CharacterManager` handles simulated "stats" and resource regeneration, providing a game-like layer to the agent's existence.
- **Reasoning Engine**: `LLMClient` (`modules/llmClient.py`) is a swappable backend (Ollama/local model, OpenAI-compatible API, etc.) — Gemma, Claude, GPT, or any future model is a reasoning engine Sarah uses, not Sarah herself. Her identity, memory, and personality persist independently of whichever model is currently plugged in.

### Behavioral Flow
`main.py` $\rightarrow$ `SarahAgent` $\rightarrow$ `SarahStateMachine` $\rightarrow$ (Personality Modifiers) $\rightarrow$ `State` (Idle/Work/Explore) $\rightarrow$ Execution of behavior.

For autonomous/conversational reasoning, `SarahStateMachine`/`sarah_cli.py` route through `ToolOrchestrator`, which loads `agents/sarah_identity.md` as the system prompt, gives the LLM the tool registry, and loops tool calls until a final answer is produced.

## Project Vision
The project aims to create a private, self-owned, and adaptive digital partner capable of managing systems and eventually interfacing with robotics, evolving its personality and decision-making style over time. The long-term "Hivemind" goal is for Sarah to extend across multiple computers, servers, services, sub-agents, and robotic bodies while remaining one continuous entity — not a fleet of independent copies.
