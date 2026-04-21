"""
Orchestrator Tools

Defines the tools the Orchestrator agent can call via the Anthropic API's
tool-use feature. Each tool has a JSON schema the model sees, and a handler
function that actually executes the action.

The handlers take a `Factory` instance and the input dict, and return a
string result that gets fed back to the orchestrator.
"""

from __future__ import annotations

import json
from typing import Any, Callable


# ── Tool definitions (sent to the API) ──────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "list_agents",
        "description": "List all agents in the factory with their role, status, and current assignment. Use this when you need to decide who to route work to.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_projects",
        "description": "List all projects in the factory. Returns their IDs, names, and status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_backlog",
        "description": "Get the list of pending tasks in a project's backlog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The project ID (e.g. 'project-alpha')",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_active_tasks",
        "description": "Get tasks currently in progress (active or in_review) for a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "create_task",
        "description": "Create a new task in a project's backlog. Use this to break down a user goal into concrete assignable work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "title": {
                    "type": "string",
                    "description": "Short imperative title (e.g. 'Build login endpoint')",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed task description including what needs to be done and any context",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Task priority",
                },
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific, checkable conditions that must be true for the task to be considered done",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization (e.g. ['backend', 'auth'])",
                },
            },
            "required": ["project_id", "title", "description"],
        },
    },
    {
        "name": "assign_task",
        "description": "Assign a task from the backlog to a specific agent. The task moves from backlog to active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_id": {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["project_id", "task_id", "agent_id"],
        },
    },
    {
        "name": "run_agent",
        "description": "Send a message to a specialist agent and get their response. Use this to actually execute work — for example, after assigning a task, run the agent to start working on it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "message": {
                    "type": "string",
                    "description": "The message to send to the agent. Typically 'Start working on your assigned task' or more specific instructions.",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional. The project this run is for. If not given, uses the agent's currently assigned project.",
                },
            },
            "required": ["agent_id", "message"],
        },
    },
    {
        "name": "submit_for_review",
        "description": "Submit a completed task for review. This moves the task from active to in_review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_id": {"type": "string"},
                "agent_id": {
                    "type": "string",
                    "description": "The agent who completed the task (the author)",
                },
            },
            "required": ["project_id", "task_id", "agent_id"],
        },
    },
    {
        "name": "record_review",
        "description": "Record a review verdict on a submitted task. The reviewer must be different from the author. Approved tasks move to done; rejected tasks stay active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_id": {"type": "string"},
                "author_agent": {"type": "string"},
                "reviewer_agent": {
                    "type": "string",
                    "description": "Must differ from author_agent",
                },
                "verdict": {
                    "type": "string",
                    "enum": ["approved", "rejected", "changes_requested"],
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the review",
                },
            },
            "required": ["project_id", "task_id", "author_agent", "reviewer_agent", "verdict"],
        },
    },
    {
        "name": "create_handoff",
        "description": "Record a structured handoff between two agents. Use this when work is passing from one specialist to another (e.g. from architect to backend-dev after design is done).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "source_agent": {"type": "string"},
                "target_agent": {"type": "string"},
                "task_id": {"type": "string"},
                "summary": {
                    "type": "string",
                    "description": "What's being handed off and why",
                },
                "what_was_done": {"type": "string"},
                "what_remains": {"type": "string"},
                "blockers": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["project_id", "source_agent", "target_agent", "task_id", "summary"],
        },
    },
    {
        "name": "record_decision",
        "description": "Record an architectural or project-level decision. This is written to both the project's decisions log and the in-repo .ai/decisions.md file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "context": {
                    "type": "string",
                    "description": "The problem or situation the decision addresses",
                },
                "decision": {
                    "type": "string",
                    "description": "What was decided",
                },
                "decided_by": {
                    "type": "string",
                    "description": "Which agent or entity made this decision",
                },
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other options that were considered and rejected",
                },
                "consequences": {
                    "type": "string",
                    "description": "Trade-offs and implications of this decision",
                },
            },
            "required": ["project_id", "title", "context", "decision", "decided_by"],
        },
    },
    {
        "name": "get_factory_status",
        "description": "Get a high-level overview of the factory: agent counts, projects, templates available.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ── Tool handlers ───────────────────────────────────────────────────────────

def _tool_list_agents(factory, _: dict) -> str:
    agents = factory.list_agents()
    # Exclude the orchestrator itself from the list — it shouldn't assign to itself
    agents = [a for a in agents if a["agent_id"] != "orchestrator"]
    if not agents:
        return "No specialist agents exist yet. Create some with create_agent first."
    lines = ["Specialist agents:"]
    for a in agents:
        lines.append(
            f"  - {a['agent_id']} (role={a['role']}, status={a['status']}, "
            f"project={a['active_project'] or 'none'}, task={a['active_task'] or 'none'})"
        )
    return "\n".join(lines)


def _tool_list_projects(factory, _: dict) -> str:
    projects = factory.config.list_projects()
    if not projects:
        return "No projects exist yet."
    lines = ["Projects:"]
    for p in projects:
        cfg = factory.config.project_config(p)
        lines.append(
            f"  - {p} (name={cfg.get('name', '?')}, status={cfg.get('status', '?')})"
        )
    return "\n".join(lines)


def _tool_get_backlog(factory, args: dict) -> str:
    tasks = factory.get_backlog(args["project_id"])
    if not tasks:
        return f"Backlog for {args['project_id']} is empty."
    lines = [f"Backlog for {args['project_id']}:"]
    for t in tasks:
        lines.append(f"  - {t['id']} [{t['priority']}]: {t['title']}")
    return "\n".join(lines)


def _tool_get_active_tasks(factory, args: dict) -> str:
    tasks = factory.get_active_tasks(args["project_id"])
    if not tasks:
        return f"No active tasks in {args['project_id']}."
    lines = [f"Active tasks in {args['project_id']}:"]
    for t in tasks:
        lines.append(
            f"  - {t['id']} [{t['status']}]: {t['title']} "
            f"(assigned_to={t.get('assigned_to', 'none')})"
        )
    return "\n".join(lines)


def _tool_create_task(factory, args: dict) -> str:
    task = factory.create_task(
        project_id=args["project_id"],
        title=args["title"],
        description=args["description"],
        priority=args.get("priority", "medium"),
        created_by="orchestrator",
        acceptance_criteria=args.get("acceptance_criteria"),
        tags=args.get("tags"),
    )
    return f"Created task {task.id}: {task.title} (priority={task.priority}) in {args['project_id']}"


def _tool_assign_task(factory, args: dict) -> str:
    try:
        task = factory.assign_task(
            project_id=args["project_id"],
            task_id=args["task_id"],
            agent_id=args["agent_id"],
        )
        return f"Assigned {args['task_id']} to {args['agent_id']}. Task is now active."
    except ValueError as e:
        return f"Error: {e}"


def _tool_run_agent(factory, args: dict) -> str:
    try:
        response = factory.run_agent(
            agent_id=args["agent_id"],
            message=args["message"],
            project_id=args.get("project_id"),
        )
        # Truncate very long responses for the orchestrator's context
        if len(response) > 3000:
            response = response[:3000] + "\n...[response truncated for brevity]"
        return f"Response from {args['agent_id']}:\n\n{response}"
    except Exception as e:
        return f"Error running agent: {e}"


def _tool_submit_for_review(factory, args: dict) -> str:
    try:
        review = factory.submit_for_review(
            project_id=args["project_id"],
            task_id=args["task_id"],
            agent_id=args["agent_id"],
        )
        return f"Task {args['task_id']} submitted for review (review-id={review['id']}). Now assign a different agent to review it."
    except Exception as e:
        return f"Error: {e}"


def _tool_record_review(factory, args: dict) -> str:
    try:
        if args["author_agent"] == args["reviewer_agent"]:
            return "Error: reviewer_agent must differ from author_agent"
        review = factory.run_review(
            project_id=args["project_id"],
            task_id=args["task_id"],
            author_agent=args["author_agent"],
            reviewer_agent=args["reviewer_agent"],
            verdict=args["verdict"],
            summary=args.get("summary", ""),
        )
        msg = f"Review recorded: {args['task_id']} → {args['verdict']}"
        if args["verdict"] == "approved":
            msg += f". Task moved to done."
        return msg
    except Exception as e:
        return f"Error: {e}"


def _tool_create_handoff(factory, args: dict) -> str:
    context = {
        "what_was_done": args.get("what_was_done", ""),
        "what_remains": args.get("what_remains", ""),
        "blockers": args.get("blockers", []),
    }
    handoff = factory.create_handoff(
        project_id=args["project_id"],
        source=args["source_agent"],
        target=args["target_agent"],
        task_id=args["task_id"],
        summary=args["summary"],
        context=context,
    )
    return f"Handoff {handoff.id} recorded: {args['source_agent']} → {args['target_agent']} for {args['task_id']}"


def _tool_record_decision(factory, args: dict) -> str:
    record = factory.add_project_decision(
        project_id=args["project_id"],
        title=args["title"],
        context=args["context"],
        decision=args["decision"],
        decided_by=args["decided_by"],
        alternatives=args.get("alternatives"),
        consequences=args.get("consequences", ""),
    )
    return f"Decision {record['id']} recorded in {args['project_id']}: {args['title']}"


def _tool_get_factory_status(factory, _: dict) -> str:
    status = factory.status()
    return json.dumps(status, indent=2)


# ── Dispatch table ──────────────────────────────────────────────────────────

TOOL_HANDLERS: dict[str, Callable[[Any, dict], str]] = {
    "list_agents": _tool_list_agents,
    "list_projects": _tool_list_projects,
    "get_backlog": _tool_get_backlog,
    "get_active_tasks": _tool_get_active_tasks,
    "create_task": _tool_create_task,
    "assign_task": _tool_assign_task,
    "run_agent": _tool_run_agent,
    "submit_for_review": _tool_submit_for_review,
    "record_review": _tool_record_review,
    "create_handoff": _tool_create_handoff,
    "record_decision": _tool_record_decision,
    "get_factory_status": _tool_get_factory_status,
}


def dispatch_tool(factory, tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return the result as a string."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Unknown tool: {tool_name}"
    try:
        return handler(factory, tool_input)
    except Exception as e:
        return f"Tool {tool_name} raised an error: {type(e).__name__}: {e}"
