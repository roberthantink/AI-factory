"""
Agent Factory

Creates new agent instances from templates, setting up their
directory structure and initial memory files.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from .config import Config
from .models import now_iso, append_jsonl


class AgentFactory:
    """Creates and manages agent instances."""

    def __init__(self, config: Config):
        self.config = config

    def create_agent(
        self,
        agent_id: str,
        template: str,
        overrides: dict | None = None,
    ) -> dict:
        """
        Create a new agent from a template.

        Args:
            agent_id: Unique ID (e.g., "agent-003")
            template: Template name (e.g., "backend-dev")
            overrides: Optional dict to override template values

        Returns:
            The agent config dict.
        """
        agent_dir = self.config.root / "agents" / agent_id
        if agent_dir.exists():
            raise ValueError(f"Agent {agent_id} already exists at {agent_dir}")

        # Load template
        tpl = self.config.agent_template(template)
        agent_cfg = {**tpl, "agent_id": agent_id, "template": template}
        if overrides:
            agent_cfg.update(overrides)

        # Create directory structure
        (agent_dir / "memory").mkdir(parents=True)
        (agent_dir / "history").mkdir(parents=True)

        # Write agent.yaml
        with open(agent_dir / "agent.yaml", "w") as f:
            yaml.dump(agent_cfg, f, default_flow_style=False, sort_keys=False)

        # Write initial state.json
        state = {
            "agent_id": agent_id,
            "status": "idle",
            "active_project": None,
            "active_task": None,
            "last_active": None,
            "total_tasks_completed": 0,
            "created_at": now_iso(),
        }
        (agent_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n")

        # Seed memory files
        role = agent_cfg.get("role", "unknown")
        spec = agent_cfg.get("specialization", "")

        append_jsonl(agent_dir / "memory" / "episodic.jsonl", {
            "id": "ep-001",
            "timestamp": now_iso(),
            "type": "system",
            "event": "agent_created",
            "summary": f"Agent {agent_id} initialized with role: {role}",
            "context": {},
            "outcome": "success",
        })

        append_jsonl(agent_dir / "memory" / "semantic.jsonl", {
            "id": "sem-001",
            "timestamp": now_iso(),
            "category": "identity",
            "fact": f"I am a {role} agent specializing in {spec}",
            "confidence": 1.0,
            "source": "config",
        })

        append_jsonl(agent_dir / "memory" / "procedural.jsonl", {
            "id": "proc-001",
            "timestamp": now_iso(),
            "category": "workflow",
            "procedure": (
                "Before starting any task: 1) Read task description and acceptance "
                "criteria, 2) Check .ai/conventions.md, 3) Check .ai/decisions.md, "
                "4) Review handoff notes. After completing: 1) Run tests, "
                "2) Submit for review, 3) Document learnings."
            ),
            "source": "template",
            "times_used": 0,
        })

        # Scratchpad
        (agent_dir / "memory" / "scratchpad.md").write_text(
            f"# {agent_id.capitalize()} Scratchpad\n\n"
            f"> Working notes. Overwritten frequently.\n\n"
            f"## Current Task\n_None assigned_\n\n"
            f"## Working Notes\n_Awaiting first assignment._\n"
        )

        # Seed history
        append_jsonl(agent_dir / "history" / f"{now_iso()[:10]}.jsonl", {
            "timestamp": now_iso(),
            "role": "system",
            "content": f"Agent {agent_id} initialized.",
        })

        return agent_cfg

    def delete_agent(self, agent_id: str) -> None:
        """Remove an agent and all its files."""
        agent_dir = self.config.root / "agents" / agent_id
        if not agent_dir.exists():
            raise ValueError(f"Agent {agent_id} does not exist")
        shutil.rmtree(agent_dir)

    def list_agents(self) -> list[dict]:
        """List all agents with their role and status."""
        result = []
        for agent_id in self.config.list_agents():
            cfg = self.config.agent_config(agent_id)
            state_path = self.config.agent_dir(agent_id) / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            result.append({
                "agent_id": agent_id,
                "role": cfg.get("role", "unknown"),
                "display_name": cfg.get("display_name", agent_id),
                "status": state.get("status", "unknown"),
                "active_project": state.get("active_project"),
                "active_task": state.get("active_task"),
                "tasks_completed": state.get("total_tasks_completed", 0),
            })
        return result
