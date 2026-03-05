"""llm247_v2: Autonomous 24/7 engineering agent with full lifecycle and GitHub workflow.

Submodule layout:
  core/          — data models, constitution, directive
  llm/           — LLM client, token tracking, audit logging, prompt templates
  storage/       — SQLite persistence (tasks, cycles, experiences)
  observability/ — centralized event emission and routing
  discovery/     — task discovery pipeline, exploration, value, interest
  execution/     — planning, safe execution, verification, git workflow
  dashboard/     — HTTP control plane and web UI server
"""
