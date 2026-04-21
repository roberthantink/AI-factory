"""
AI Factory — Main Entry Point

Top-level Factory class that ties all components together.

This is the Python-level API. For the smart conversational interface,
talk to the Orchestrator Agent via `factory.chat_with_orchestrator(...)`
or the `python cli.py chat` command.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .config import Config
from .context_assembler import ContextAssembler
from .memory_manager import MemoryManager
from .memory_compactor import MemoryCompactor
from .scheduler import Scheduler
from .review_router import ReviewRouter
from .agent_factory import AgentFactory
from .llm_client import LLMClient
from .orchestrator_tools import TOOL_DEFINITIONS, dispatch_tool

logger = logging.getLogger("ai-factory")


class Factory:
    """
    Top-level orchestrator for the AI Factory.
    """

    def __init__(self, root: str | Path, log_level: str | None = None):
        self.root = Path(root).resolve()
        self.config = Config(self.root)

        level = log_level or self.config.factory.get("factory", {}).get("log_level", "INFO")
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

        self.memory = MemoryManager(self.config)
        self.assembler = ContextAssembler(self.config)
        self.scheduler = Scheduler(self.config, self.memory)
        self.reviews = ReviewRouter(self.config, self.memory, self.scheduler)
        self.agents = AgentFactory(self.config)
        self.llm = LLMClient(self.config, self.assembler, self.memory)
        self.compactor = MemoryCompactor(
            self.config,
            llm_caller=lambda prompt: self.llm.simple_completion(prompt),
        )

        # Orchestrator conversation state — preserved across chat turns
        self._orchestrator_history: list[dict] = []

        logger.info(f"AI Factory initialized at {self.root}")
        logger.info(f"Agents: {self.config.list_agents()}")
        logger.info(f"Projects: {self.config.list_projects()}")

    # ── Agent management ────────────────────────────────────────────────

    def create_agent(self, agent_id: str, template: str, **overrides) -> dict:
        cfg = self.agents.create_agent(agent_id, template, overrides or None)
        self.config.reload()
        logger.info(f"Created agent {agent_id} from template '{template}'")
        return cfg

    def list_agents(self) -> list[dict]:
        return self.agents.list_agents()

    def delete_agent(self, agent_id: str) -> None:
        self.agents.delete_agent(agent_id)
        self.config.reload()
        logger.info(f"Deleted agent {agent_id}")

    # ── Task management ─────────────────────────────────────────────────

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str,
        priority: str = "medium",
        created_by: str = "human",
        acceptance_criteria: list[str] | None = None,
        tags: list[str] | None = None,
    ):
        task = self.scheduler.create_task(
            project_id, title, description, priority,
            created_by, acceptance_criteria, tags=tags,
        )
        logger.info(f"Created task {task.id} in {project_id}: {title}")
        return task

    def assign_task(self, project_id: str, task_id: str, agent_id: str) -> dict:
        task = self.scheduler.assign_task(project_id, task_id, agent_id)
        logger.info(f"Assigned {task_id} to {agent_id} in {project_id}")
        return task

    def get_backlog(self, project_id: str) -> list[dict]:
        return self.scheduler.get_backlog(project_id)

    def get_active_tasks(self, project_id: str) -> list[dict]:
        return self.scheduler.get_active_tasks(project_id)

    def get_done_tasks(self, project_id: str) -> list[dict]:
        return self.scheduler.get_done_tasks(project_id)

    # ── Run a specialist agent ──────────────────────────────────────────

    def run_agent(
        self,
        agent_id: str,
        message: str,
        project_id: str | None = None,
        tier: str = "L1",
    ) -> str:
        """Send a message to a specialist agent (no tool use)."""
        if project_id is None:
            state = self.memory.get_agent_state(agent_id)
            project_id = state.get("active_project")

        task_desc = ""
        if project_id:
            task = self.scheduler.get_agent_active_task(agent_id, project_id)
            if task:
                task_desc = task.get("description", "")

        response = self.llm.run_agent(
            agent_id=agent_id,
            user_message=message,
            project_id=project_id,
            tier=tier,
            task_description=task_desc,
        )
        logger.info(f"Agent {agent_id} responded ({len(response)} chars)")
        return response

    # ── Chat with the Orchestrator Agent ────────────────────────────────

    def chat_with_orchestrator(
        self,
        message: str,
        project_id: str | None = None,
        on_tool_call: Callable[[str, dict, str], None] | None = None,
        reset_history: bool = False,
    ) -> str:
        """
        Send a message to the Orchestrator Agent and get a response.

        The orchestrator has access to tools to actually perform actions.
        Conversation history is preserved across calls unless reset_history=True.

        Args:
            message: User's message
            project_id: Optional project context to load
            on_tool_call: Optional callback to observe each tool call. Signature:
                          on_tool_call(tool_name, tool_input, result)
            reset_history: If True, clears the conversation history before responding

        Returns:
            The orchestrator's final text response.
        """
        if reset_history:
            self._orchestrator_history = []

        def dispatcher(tool_name: str, tool_input: dict) -> str:
            return dispatch_tool(self, tool_name, tool_input)

        final_text, updated_history = self.llm.run_agent_with_tools(
            agent_id="orchestrator",
            user_message=message,
            tools=TOOL_DEFINITIONS,
            tool_dispatcher=dispatcher,
            conversation_history=self._orchestrator_history,
            project_id=project_id,
            tier="L1",
            on_tool_call=on_tool_call,
        )

        self._orchestrator_history = updated_history
        logger.info(f"Orchestrator responded ({len(final_text)} chars)")
        return final_text

    def reset_orchestrator_conversation(self) -> None:
        """Clear the orchestrator's in-memory conversation history."""
        self._orchestrator_history = []

    # ── Review flow ─────────────────────────────────────────────────────

    def submit_for_review(self, project_id: str, task_id: str, agent_id: str) -> dict:
        review = self.scheduler.submit_for_review(project_id, task_id, agent_id)
        logger.info(f"Task {task_id} submitted for review by {agent_id}")
        return review

    def run_review(
        self,
        project_id: str,
        task_id: str,
        author_agent: str,
        reviewer_agent: str,
        verdict: str,
        comments: list[dict] | None = None,
        summary: str = "",
    ):
        review = self.reviews.submit_review(
            project_id, task_id, author_agent,
            reviewer_agent, verdict, comments, summary,
        )
        logger.info(f"Review {review.id}: {task_id} {verdict} by {reviewer_agent}")
        return review

    # ── Memory operations ───────────────────────────────────────────────

    def add_agent_learning(self, agent_id: str, fact: str, category: str = "pattern"):
        return self.memory.add_semantic(agent_id, category, fact)

    def add_project_decision(self, project_id: str, title: str, context: str,
                              decision: str, decided_by: str, **kwargs):
        return self.memory.add_project_decision(
            project_id, title, context, decision, decided_by, **kwargs,
        )

    def compact_memory(self, agent_id: str | None = None) -> dict:
        if agent_id:
            return {agent_id: self.compactor.compact_agent_episodic(agent_id)}
        return self.compactor.compact_all_agents()

    def create_handoff(self, project_id: str, source: str, target: str,
                       task_id: str, summary: str, context: dict | None = None):
        return self.memory.create_handoff(
            project_id, source, target, task_id, summary, context,
        )

    # ── Status ──────────────────────────────────────────────────────────

    def status(self) -> dict:
        agents = self.list_agents()
        projects = self.config.list_projects()
        return {
            "factory_root": str(self.root),
            "agents": {
                "total": len(agents),
                "idle": sum(1 for a in agents if a["status"] == "idle"),
                "working": sum(1 for a in agents if a["status"] == "working"),
                "details": agents,
            },
            "projects": {
                "total": len(projects),
                "ids": projects,
            },
            "templates": self.config.list_templates(),
        }
