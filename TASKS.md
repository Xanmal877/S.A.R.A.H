# 📝 S.A.R.A.H. Task List

## ✅ Completed
- [x] Initialize project environment
- [x] Fix import errors in `agents/sarah.py` and `agents/baseAgent.py`
- [x] Verify that `main.py` runs and S.A.R.A.H. starts successfully
- [x] Add missing `__init__.py` to packages
- [x] Implement Capability Suite in `stateMachine.py` (Reasoned Actions foundation)

## ⚠️ Issues
- [ ] None (Current boot issues resolved)

## 📅 Planned
- [ ] **Phase 1: LLM Integration Layer**
    - [ ] Implement `modules/llmClient.py` (Ollama/API connection)
    - [ ] Implement `PersonaMapper` (Traits $\to$ Prompt)
    - [ ] Implement `DecisionSchema` (JSON parsing/validation)
- [ ] **Phase 2: Rewiring the State Machine**
    - [ ] Update `mainAgent.py` to use LLM for decision making
    - [ ] Refactor `stateMachine.py` to accept `action_name`
    - [ ] Implement fallback to probabilistic logic
- [ ] **Phase 3: Context Aggregation**
    - [ ] Implement `ObservationModule` (World State compilation)
- [ ] **Phase 4: Personality-Driven Output**
    - [ ] Integrate LLM `thought` field into output
    - [ ] Implement MBTI-based Voice Filters
- [ ] Expand personality module with more nuanced traits
- [ ] Create basic system control capabilities
- [ ] Fully integrate LLM reasoning (Final Polish)
