"""
Memory Manager

Handles reading and writing to agent and project memory files.
Provides a clean API so the rest of the orchestrator doesn't
need to know about file paths or JSONL formatting.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .models import (
    EpisodicEntry,
    SemanticEntry,
    ProceduralEntry,
    Handoff,
    Review,
    append_jsonl,
    read_jsonl,
    next_id,
    now_iso,
)


class MemoryManager:
    """Read/write interface for agent and project memory."""

    def __init__(self, config: Config):
        self.config = config

    # ── Agent memory ────────────────────────────────────────────────────

    def add_episodic(
        self,
        agent_id: str,
        event: str,
        summary: str,
        outcome: str,
        type_: str = "task",
        context: dict | None = None,
        related_task: str | None = None,
        related_project: str | None = None,
    ) -> EpisodicEntry:
        path = self.config.agent_dir(agent_id) / "memory" / "episodic.jsonl"
        entry = EpisodicEntry(
            id=next_id("ep", path),
            timestamp=now_iso(),
            type=type_,
            event=event,
            summary=summary,
            outcome=outcome,
            context=context or {},
            related_task=related_task,
            related_project=related_project,
        )
        append_jsonl(path, entry.to_dict())
        return entry

    def add_semantic(
        self,
        agent_id: str,
        category: str,
        fact: str,
        confidence: float = 1.0,
        source: str = "agent",
        supersedes: str | None = None,
    ) -> SemanticEntry:
        path = self.config.agent_dir(agent_id) / "memory" / "semantic.jsonl"
        entry = SemanticEntry(
            id=next_id("sem", path),
            timestamp=now_iso(),
            category=category,
            fact=fact,
            confidence=confidence,
            source=source,
            supersedes=supersedes,
        )
        append_jsonl(path, entry.to_dict())
        return entry

    def add_procedural(
        self,
        agent_id: str,
        category: str,
        procedure: str,
        source: str = "agent",
    ) -> ProceduralEntry:
        path = self.config.agent_dir(agent_id) / "memory" / "procedural.jsonl"
        entry = ProceduralEntry(
            id=next_id("proc", path),
            timestamp=now_iso(),
            category=category,
            procedure=procedure,
            source=source,
        )
        append_jsonl(path, entry.to_dict())
        return entry

    def get_episodic(self, agent_id: str, limit: int | None = None) -> list[dict]:
        path = self.config.agent_dir(agent_id) / "memory" / "episodic.jsonl"
        return read_jsonl(path, limit=limit)

    def get_semantic(self, agent_id: str, limit: int | None = None) -> list[dict]:
        path = self.config.agent_dir(agent_id) / "memory" / "semantic.jsonl"
        return read_jsonl(path, limit=limit)

    def get_procedural(self, agent_id: str, limit: int | None = None) -> list[dict]:
        path = self.config.agent_dir(agent_id) / "memory" / "procedural.jsonl"
        return read_jsonl(path, limit=limit)

    def update_scratchpad(self, agent_id: str, content: str) -> None:
        path = self.config.agent_dir(agent_id) / "memory" / "scratchpad.md"
        path.write_text(content)

    def get_scratchpad(self, agent_id: str) -> str:
        path = self.config.agent_dir(agent_id) / "memory" / "scratchpad.md"
        return path.read_text() if path.exists() else ""

    # ── Agent state ─────────────────────────────────────────────────────

    def get_agent_state(self, agent_id: str) -> dict:
        import json
        path = self.config.agent_dir(agent_id) / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def update_agent_state(self, agent_id: str, updates: dict) -> dict:
        import json
        path = self.config.agent_dir(agent_id) / "state.json"
        state = self.get_agent_state(agent_id)
        state.update(updates)
        path.write_text(json.dumps(state, indent=2) + "\n")
        return state

    # ── Project memory ──────────────────────────────────────────────────

    def add_project_decision(
        self,
        project_id: str,
        title: str,
        context: str,
        decision: str,
        decided_by: str,
        alternatives: list[str] | None = None,
        consequences: str = "",
    ) -> dict:
        path = self.config.project_dir(project_id) / "memory" / "decisions.jsonl"
        record = {
            "id": next_id("dec", path),
            "timestamp": now_iso(),
            "title": title,
            "context": context,
            "decision": decision,
            "alternatives_considered": alternatives or [],
            "consequences": consequences,
            "decided_by": decided_by,
        }
        append_jsonl(path, record)

        # Also append to the in-repo markdown
        md_path = self.config.workspace_dir(project_id) / ".ai" / "decisions.md"
        if md_path.exists():
            alts = "\n".join(f"  - {a}" for a in (alternatives or []))
            block = (
                f"\n\n---\n\n"
                f"## {record['id'].upper()}: {title}\n\n"
                f"- **Date:** {record['timestamp'][:10]}\n"
                f"- **Status:** Accepted\n"
                f"- **Decided by:** {decided_by}\n"
                f"- **Context:** {context}\n"
                f"- **Decision:** {decision}\n"
            )
            if alts:
                block += f"- **Alternatives considered:**\n{alts}\n"
            if consequences:
                block += f"- **Consequences:** {consequences}\n"
            with open(md_path, "a") as f:
                f.write(block)

        return record

    def add_project_knowledge(
        self,
        project_id: str,
        fact: str,
        category: str = "project",
        source: str = "agent",
    ) -> dict:
        path = self.config.project_dir(project_id) / "memory" / "knowledge.jsonl"
        record = {
            "id": next_id("know", path),
            "timestamp": now_iso(),
            "category": category,
            "fact": fact,
            "source": source,
        }
        append_jsonl(path, record)
        return record

    def add_timeline_event(
        self,
        project_id: str,
        event: str,
        summary: str,
        agents_involved: list[str] | None = None,
        details: dict | None = None,
    ) -> dict:
        path = self.config.project_dir(project_id) / "memory" / "timeline.jsonl"
        record = {
            "id": next_id("tl", path),
            "timestamp": now_iso(),
            "event": event,
            "summary": summary,
            "agents_involved": agents_involved or [],
            "details": details or {},
        }
        append_jsonl(path, record)
        return record

    # ── Handoffs ────────────────────────────────────────────────────────

    def create_handoff(
        self,
        project_id: str,
        source_agent: str,
        target_agent: str,
        task_id: str,
        summary: str,
        context: dict | None = None,
    ) -> Handoff:
        path = self.config.project_dir(project_id) / "comms" / "handoffs.jsonl"
        handoff = Handoff(
            id=next_id("ho", path),
            timestamp=now_iso(),
            source_agent=source_agent,
            target_agent=target_agent,
            task_id=task_id,
            summary=summary,
            context=context or {},
        )
        append_jsonl(path, handoff.to_dict())
        return handoff

    # ── Reviews ─────────────────────────────────────────────────────────

    def submit_for_review(
        self,
        project_id: str,
        task_id: str,
        author_agent: str,
    ) -> dict:
        path = self.config.project_dir(project_id) / "reviews" / "pending.jsonl"
        record = {
            "id": next_id("rev", path),
            "timestamp": now_iso(),
            "task_id": task_id,
            "author_agent": author_agent,
            "status": "pending",
        }
        append_jsonl(path, record)
        return record

    def complete_review(
        self,
        project_id: str,
        review: Review,
    ) -> None:
        path = self.config.project_dir(project_id) / "reviews" / "completed.jsonl"
        append_jsonl(path, review.to_dict())

    # ── Conversation history ────────────────────────────────────────────

    def append_history(
        self,
        agent_id: str,
        role: str,
        content: str,
    ) -> None:
        from datetime import date
        today = date.today().isoformat()
        path = self.config.agent_dir(agent_id) / "history" / f"{today}.jsonl"
        append_jsonl(path, {
            "timestamp": now_iso(),
            "role": role,
            "content": content,
        })

    def get_history(
        self,
        agent_id: str,
        date_str: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        from datetime import date
        if date_str is None:
            date_str = date.today().isoformat()
        path = self.config.agent_dir(agent_id) / "history" / f"{date_str}.jsonl"
        return read_jsonl(path, limit=limit)
