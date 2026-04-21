"""
Scheduler

Manages the task lifecycle:
  - Assigns agents to tasks from the backlog
  - Moves tasks between backlog → active → in_review → done
  - Routes completed tasks to reviewers
  - Respects quality gates (review required, tests required)
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .models import Task, read_jsonl, append_jsonl, now_iso
from .memory_manager import MemoryManager


class Scheduler:
    """Assigns tasks to agents and manages task state transitions."""

    def __init__(self, config: Config, memory: MemoryManager):
        self.config = config
        self.memory = memory

    # ── Task queries ────────────────────────────────────────────────────

    def get_backlog(self, project_id: str) -> list[dict]:
        path = self.config.project_dir(project_id) / "tasks" / "backlog.jsonl"
        return read_jsonl(path)

    def get_active_tasks(self, project_id: str) -> list[dict]:
        path = self.config.project_dir(project_id) / "tasks" / "active.jsonl"
        return read_jsonl(path)

    def get_done_tasks(self, project_id: str) -> list[dict]:
        path = self.config.project_dir(project_id) / "tasks" / "done.jsonl"
        return read_jsonl(path)

    def get_agent_active_task(self, agent_id: str, project_id: str) -> dict | None:
        tasks = self.get_active_tasks(project_id)
        for t in tasks:
            if t.get("assigned_to") == agent_id:
                return t
        return None

    # ── Task creation ───────────────────────────────────────────────────

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str,
        priority: str = "medium",
        created_by: str = "human",
        acceptance_criteria: list[str] | None = None,
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        path = self.config.project_dir(project_id) / "tasks" / "backlog.jsonl"
        task = Task(
            id=f"task-{self._count_all_tasks(project_id) + 1:03d}",
            title=title,
            description=description,
            priority=priority,
            created_by=created_by,
            acceptance_criteria=acceptance_criteria or [],
            depends_on=depends_on or [],
            tags=tags or [],
        )
        append_jsonl(path, task.to_dict())

        self.memory.add_timeline_event(
            project_id,
            event="task_created",
            summary=f"Task {task.id} created: {title}",
            agents_involved=[],
            details={"task_id": task.id, "created_by": created_by},
        )
        return task

    # ── Assignment ──────────────────────────────────────────────────────

    def assign_task(
        self,
        project_id: str,
        task_id: str,
        agent_id: str,
    ) -> dict:
        """
        Move a task from backlog to active and assign it to an agent.

        Returns the updated task dict.
        """
        backlog_path = self.config.project_dir(project_id) / "tasks" / "backlog.jsonl"
        active_path = self.config.project_dir(project_id) / "tasks" / "active.jsonl"

        # Find and remove from backlog
        backlog = read_jsonl(backlog_path)
        task = None
        remaining = []
        for t in backlog:
            if t["id"] == task_id:
                task = t
            else:
                remaining.append(t)

        if task is None:
            raise ValueError(f"Task {task_id} not found in backlog for {project_id}")

        # Check dependencies
        done_ids = {t["id"] for t in self.get_done_tasks(project_id)}
        for dep in task.get("depends_on", []):
            if dep not in done_ids:
                raise ValueError(
                    f"Task {task_id} depends on {dep} which is not done yet"
                )

        # Update task
        task["status"] = "active"
        task["assigned_to"] = agent_id

        # Write back
        self._rewrite_jsonl(backlog_path, remaining)
        append_jsonl(active_path, task)

        # Update agent state
        self.memory.update_agent_state(agent_id, {
            "status": "working",
            "active_project": project_id,
            "active_task": task_id,
            "last_active": now_iso(),
        })

        self.memory.add_timeline_event(
            project_id,
            event="task_assigned",
            summary=f"Task {task_id} assigned to {agent_id}",
            agents_involved=[agent_id],
            details={"task_id": task_id},
        )

        return task

    # ── Task completion ─────────────────────────────────────────────────

    def submit_for_review(self, project_id: str, task_id: str, agent_id: str) -> dict:
        """Move a task from active to in_review."""
        active_path = self.config.project_dir(project_id) / "tasks" / "active.jsonl"
        active = read_jsonl(active_path)

        task = None
        remaining = []
        for t in active:
            if t["id"] == task_id:
                task = t
            else:
                remaining.append(t)

        if task is None:
            raise ValueError(f"Task {task_id} not found in active tasks")

        task["status"] = "in_review"
        remaining.append(task)  # Keep in active file but with new status
        self._rewrite_jsonl(active_path, remaining)

        review = self.memory.submit_for_review(project_id, task_id, agent_id)

        self.memory.add_timeline_event(
            project_id,
            event="task_submitted_for_review",
            summary=f"Task {task_id} submitted for review by {agent_id}",
            agents_involved=[agent_id],
        )

        return review

    def complete_task(self, project_id: str, task_id: str) -> dict:
        """Move a task from active to done."""
        active_path = self.config.project_dir(project_id) / "tasks" / "active.jsonl"
        done_path = self.config.project_dir(project_id) / "tasks" / "done.jsonl"

        active = read_jsonl(active_path)
        task = None
        remaining = []
        for t in active:
            if t["id"] == task_id:
                task = t
            else:
                remaining.append(t)

        if task is None:
            raise ValueError(f"Task {task_id} not found in active tasks")

        task["status"] = "done"
        task["completed_at"] = now_iso()

        self._rewrite_jsonl(active_path, remaining)
        append_jsonl(done_path, task)

        # Update agent state
        agent_id = task.get("assigned_to")
        if agent_id:
            state = self.memory.get_agent_state(agent_id)
            self.memory.update_agent_state(agent_id, {
                "status": "idle",
                "active_project": None,
                "active_task": None,
                "total_tasks_completed": state.get("total_tasks_completed", 0) + 1,
                "last_active": now_iso(),
            })

        self.memory.add_timeline_event(
            project_id,
            event="task_completed",
            summary=f"Task {task_id} completed",
            agents_involved=[agent_id] if agent_id else [],
        )

        return task

    # ── Review routing ──────────────────────────────────────────────────

    def find_reviewer(self, project_id: str, author_agent: str) -> str | None:
        """
        Find an available agent to review work.

        Rules:
          1. Reviewer must not be the author
          2. Reviewer should have review capability or be the architect
          3. Prefer idle agents
        """
        project_cfg = self.config.project_config(project_id)
        assigned = project_cfg.get("assigned_agents", [])

        candidates = []
        for a in assigned:
            aid = a["agent_id"]
            if aid == author_agent:
                continue
            state = self.memory.get_agent_state(aid)
            agent_cfg = self.config.agent_config(aid)
            caps = agent_cfg.get("capabilities", [])
            is_reviewer = "code_review" in caps or agent_cfg.get("role") == "reviewer"
            is_idle = state.get("status") == "idle"
            candidates.append((aid, is_reviewer, is_idle))

        # Sort: prefer reviewers, then idle agents
        candidates.sort(key=lambda c: (not c[1], not c[2]))

        return candidates[0][0] if candidates else None

    # ── Helpers ─────────────────────────────────────────────────────────

    def _count_all_tasks(self, project_id: str) -> int:
        base = self.config.project_dir(project_id) / "tasks"
        count = 0
        for f in ("backlog.jsonl", "active.jsonl", "done.jsonl"):
            count += len(read_jsonl(base / f))
        return count

    @staticmethod
    def _rewrite_jsonl(path: Path, entries: list[dict]) -> None:
        with open(path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
