"""
Context Assembler

Builds the context window content for an agent by merging:
  - Agent identity and config (L0)
  - Project conventions and decisions (L1)
  - Deep memory via search (L2)

The assembled context is a list of content blocks that get prepended
to the agent's system prompt before calling the LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .models import read_jsonl


class ContextAssembler:
    """Assembles tiered context for an agent working on a project."""

    def __init__(self, config: Config):
        self.config = config

    def assemble(
        self,
        agent_id: str,
        project_id: str | None = None,
        task_description: str = "",
        tier: str = "L1",
    ) -> str:
        """
        Build the full context string for an agent.

        Args:
            agent_id: Which agent is being given context
            project_id: Which project they're working on (None for unassigned)
            task_description: Current task (used for L2 semantic search)
            tier: Maximum tier to load — "L0", "L1", or "L2"

        Returns:
            A single string to inject into the system prompt.
        """
        blocks: list[str] = []

        # ── L0: Always loaded ───────────────────────────────────────────
        blocks.append(self._load_agent_identity(agent_id))
        blocks.append(self._load_agent_state(agent_id))

        if project_id:
            blocks.append(self._load_active_task(agent_id, project_id))

        if tier in ("L0",):
            return self._join(blocks)

        # ── L1: Project context ─────────────────────────────────────────
        if project_id:
            blocks.append(self._load_conventions(project_id))
            blocks.append(self._load_decisions(project_id))
            blocks.append(self._load_handoffs(agent_id, project_id))

        blocks.append(self._load_agent_semantic_memory(agent_id))
        blocks.append(self._load_agent_procedural_memory(agent_id))

        if tier in ("L1",):
            return self._join(blocks)

        # ── L2: Deep context ───────────────────────────────────────────
        blocks.append(self._load_agent_episodic_memory(agent_id))

        if project_id:
            blocks.append(self._load_project_knowledge(project_id))
            blocks.append(self._load_project_timeline(project_id))
            blocks.append(self._load_review_history(project_id))

        blocks.append(self._load_shared_knowledge())

        return self._join(blocks)

    # ── L0 loaders ──────────────────────────────────────────────────────

    def _load_agent_identity(self, agent_id: str) -> str:
        cfg = self.config.agent_config(agent_id)
        role = cfg.get("role", "unknown")
        spec = cfg.get("specialization", "")
        return f"<agent_identity>\nRole: {role}\nSpecialization: {spec}\n</agent_identity>"

    def _load_agent_state(self, agent_id: str) -> str:
        import json
        state_path = self.config.agent_dir(agent_id) / "state.json"
        if not state_path.exists():
            return ""
        state = json.loads(state_path.read_text())
        status = state.get("status", "unknown")
        project = state.get("active_project", "none")
        task = state.get("active_task", "none")
        return (
            f"<agent_state>\n"
            f"Status: {status}\n"
            f"Active project: {project}\n"
            f"Active task: {task}\n"
            f"</agent_state>"
        )

    def _load_active_task(self, agent_id: str, project_id: str) -> str:
        path = self.config.project_dir(project_id) / "tasks" / "active.jsonl"
        tasks = read_jsonl(path)
        my_tasks = [t for t in tasks if t.get("assigned_to") == agent_id]
        if not my_tasks:
            return "<active_task>No active task assigned.</active_task>"
        t = my_tasks[0]
        criteria = "\n".join(f"  - {c}" for c in t.get("acceptance_criteria", []))
        return (
            f"<active_task>\n"
            f"Task: {t['id']} — {t['title']}\n"
            f"Description: {t['description']}\n"
            f"Priority: {t.get('priority', 'medium')}\n"
            f"Acceptance criteria:\n{criteria}\n"
            f"</active_task>"
        )

    # ── L1 loaders ──────────────────────────────────────────────────────

    def _load_conventions(self, project_id: str) -> str:
        path = self.config.workspace_dir(project_id) / ".ai" / "conventions.md"
        if not path.exists():
            return ""
        content = path.read_text().strip()
        return f"<project_conventions>\n{content}\n</project_conventions>"

    def _load_decisions(self, project_id: str, limit: int = 20) -> str:
        # Read from the in-repo markdown version
        path = self.config.workspace_dir(project_id) / ".ai" / "decisions.md"
        if not path.exists():
            return ""
        content = path.read_text().strip()
        # Truncate to last N decision blocks if very long
        blocks = content.split("\n---\n")
        if len(blocks) > limit:
            blocks = blocks[:1] + blocks[-limit:]  # Keep header + last N
        return f"<project_decisions>\n{'---'.join(blocks)}\n</project_decisions>"

    def _load_handoffs(self, agent_id: str, project_id: str, limit: int = 5) -> str:
        path = self.config.project_dir(project_id) / "comms" / "handoffs.jsonl"
        entries = read_jsonl(path, limit=limit)
        mine = [e for e in entries if e.get("target_agent") == agent_id]
        if not mine:
            return ""
        parts = []
        for h in mine:
            ctx = h.get("context", {})
            parts.append(
                f"From {h['source_agent']} re: task {h['task_id']}:\n"
                f"  Summary: {h['summary']}\n"
                f"  Done: {ctx.get('what_was_done', 'N/A')}\n"
                f"  Remaining: {ctx.get('what_remains', 'N/A')}\n"
                f"  Blockers: {', '.join(ctx.get('blockers', [])) or 'None'}"
            )
        return f"<handoffs>\n" + "\n\n".join(parts) + "\n</handoffs>"

    def _load_agent_semantic_memory(self, agent_id: str, limit: int = 50) -> str:
        path = self.config.agent_dir(agent_id) / "memory" / "semantic.jsonl"
        entries = read_jsonl(path, limit=limit)
        if not entries:
            return ""
        facts = "\n".join(
            f"- [{e.get('category', '?')}] {e['fact']} (confidence: {e.get('confidence', '?')})"
            for e in entries
        )
        return f"<agent_knowledge>\n{facts}\n</agent_knowledge>"

    def _load_agent_procedural_memory(self, agent_id: str, limit: int = 20) -> str:
        path = self.config.agent_dir(agent_id) / "memory" / "procedural.jsonl"
        entries = read_jsonl(path, limit=limit)
        if not entries:
            return ""
        procs = "\n".join(
            f"- [{e.get('category', '?')}] {e['procedure']}"
            for e in entries
        )
        return f"<agent_procedures>\n{procs}\n</agent_procedures>"

    # ── L2 loaders ──────────────────────────────────────────────────────

    def _load_agent_episodic_memory(self, agent_id: str, limit: int = 10) -> str:
        path = self.config.agent_dir(agent_id) / "memory" / "episodic.jsonl"
        entries = read_jsonl(path, limit=limit)
        if not entries:
            return ""
        episodes = "\n".join(
            f"- [{e.get('timestamp', '?')}] {e.get('event', '?')}: "
            f"{e.get('summary', '')} → {e.get('outcome', '?')}"
            for e in entries
        )
        return f"<agent_history>\n{episodes}\n</agent_history>"

    def _load_project_knowledge(self, project_id: str, limit: int = 15) -> str:
        path = self.config.project_dir(project_id) / "memory" / "knowledge.jsonl"
        entries = read_jsonl(path, limit=limit)
        if not entries:
            return ""
        facts = "\n".join(f"- {e['fact']}" for e in entries if "fact" in e)
        return f"<project_knowledge>\n{facts}\n</project_knowledge>"

    def _load_project_timeline(self, project_id: str, limit: int = 30) -> str:
        path = self.config.project_dir(project_id) / "memory" / "timeline.jsonl"
        entries = read_jsonl(path, limit=limit)
        if not entries:
            return ""
        events = "\n".join(
            f"- [{e.get('timestamp', '?')}] {e.get('summary', '')}"
            for e in entries
        )
        return f"<project_timeline>\n{events}\n</project_timeline>"

    def _load_review_history(self, project_id: str, limit: int = 10) -> str:
        path = self.config.project_dir(project_id) / "reviews" / "completed.jsonl"
        entries = read_jsonl(path, limit=limit)
        if not entries:
            return ""
        reviews = "\n".join(
            f"- Task {e.get('task_id', '?')}: {e.get('verdict', '?')} "
            f"by {e.get('reviewer_agent', '?')} — {e.get('summary', '')}"
            for e in entries
        )
        return f"<review_history>\n{reviews}\n</review_history>"

    def _load_shared_knowledge(self) -> str:
        path = self.config.root / "shared" / "knowledge"
        if not path.exists():
            return ""
        parts = []
        for f in sorted(path.glob("*.md")):
            if f.name == "README.md":
                continue
            parts.append(f.read_text().strip())
        for f in sorted(path.glob("*.jsonl")):
            entries = read_jsonl(f, limit=10)
            for e in entries:
                if "fact" in e:
                    parts.append(f"- {e['fact']}")
        if not parts:
            return ""
        return f"<shared_knowledge>\n" + "\n\n".join(parts) + "\n</shared_knowledge>"

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _join(blocks: list[str]) -> str:
        """Join non-empty blocks with double newlines."""
        return "\n\n".join(b for b in blocks if b.strip())
