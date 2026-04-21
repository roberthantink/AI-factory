#!/usr/bin/env python3
"""
AI Factory CLI

Commands:

  # The main way to use the factory — chat with the Orchestrator Agent
  python cli.py chat                            # Start an interactive chat session
  python cli.py ask "I want to build ..."       # One-shot question to the Orchestrator

  # Direct (manual) commands — useful for debugging or when you want fine control
  python cli.py status
  python cli.py agents
  python cli.py templates
  python cli.py create-agent <agent-id> <template>
  python cli.py delete-agent <agent-id>
  python cli.py projects
  python cli.py backlog <project-id>
  python cli.py create-task <project-id> "<title>" "<description>"
  python cli.py assign <project-id> <task-id> <agent-id>
  python cli.py run <agent-id> "<message>" [project-id]
  python cli.py compact [agent-id]
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

FACTORY_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(FACTORY_ROOT))

from orchestrator.main import Factory


# ── Orchestrator chat ──────────────────────────────────────────────────────

def _print_tool_call(name: str, args: dict, result: str) -> None:
    """Pretty-print a tool call as it happens so the user can see what's going on."""
    print(f"\n  \033[2m→ [{name}] {_summarize_args(args)}\033[0m")
    # Show a short preview of the result
    first_line = result.split("\n")[0][:120]
    print(f"  \033[2m  ← {first_line}\033[0m")


def _summarize_args(args: dict) -> str:
    """Compact single-line summary of tool args."""
    parts = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 60:
            v = v[:57] + "..."
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def cmd_chat(factory: Factory) -> None:
    """Interactive chat session with the Orchestrator Agent."""
    print("┌─────────────────────────────────────────────────────────────┐")
    print("│  AI Factory — Chat with the Orchestrator                    │")
    print("│                                                             │")
    print("│  Describe what you want. The Orchestrator will decompose    │")
    print("│  tasks, assign them to specialist agents, and coordinate.   │")
    print("│                                                             │")
    print("│  Type 'exit', 'quit', or Ctrl-D to leave.                   │")
    print("│  Type 'reset' to clear the conversation history.            │")
    print("└─────────────────────────────────────────────────────────────┘\n")

    while True:
        try:
            message = input("\n\033[1myou>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not message:
            continue
        if message.lower() in ("exit", "quit"):
            print("Bye.")
            break
        if message.lower() == "reset":
            factory.reset_orchestrator_conversation()
            print("Conversation history cleared.")
            continue

        print("\n\033[1morchestrator>\033[0m", end=" ", flush=True)
        try:
            response = factory.chat_with_orchestrator(
                message,
                on_tool_call=_print_tool_call,
            )
        except Exception as e:
            print(f"\n\033[31mError: {e}\033[0m")
            continue
        print(response)


def cmd_ask(factory: Factory, message: str) -> None:
    """One-shot question to the Orchestrator."""
    print(f"\n\033[1myou>\033[0m {message}\n")
    print("\033[1morchestrator>\033[0m", end=" ", flush=True)
    response = factory.chat_with_orchestrator(
        message,
        on_tool_call=_print_tool_call,
    )
    print(response)


# ── Main CLI dispatch ──────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    factory = Factory(FACTORY_ROOT)

    # ── Orchestrator chat (primary interface) ──────────────────────────

    if cmd == "chat":
        cmd_chat(factory)
        return

    if cmd == "ask":
        if len(args) < 2:
            print('Usage: ask "<message>"')
            return
        cmd_ask(factory, args[1])
        return

    # ── Direct commands ────────────────────────────────────────────────

    if cmd == "status":
        status = factory.status()
        print(json.dumps(status, indent=2))

    elif cmd == "agents":
        for a in factory.list_agents():
            status = a["status"]
            task = a["active_task"] or "-"
            proj = a["active_project"] or "-"
            done = a["tasks_completed"]
            print(f"  {a['agent_id']:14s}  {a['role']:14s}  {status:8s}  project={proj}  task={task}  done={done}")

    elif cmd == "create-agent":
        if len(args) < 3:
            print("Usage: create-agent <agent-id> <template>")
            return
        factory.create_agent(args[1], args[2])
        print(f"Created agent {args[1]} from template '{args[2]}'")

    elif cmd == "delete-agent":
        if len(args) < 2:
            print("Usage: delete-agent <agent-id>")
            return
        factory.delete_agent(args[1])
        print(f"Deleted agent {args[1]}")

    elif cmd == "projects":
        for p in factory.config.list_projects():
            cfg = factory.config.project_config(p)
            assigned = len(cfg.get("assigned_agents", []))
            print(f"  {p:20s}  {cfg.get('status', '?'):8s}  agents={assigned}")

    elif cmd == "backlog":
        if len(args) < 2:
            print("Usage: backlog <project-id>")
            return
        tasks = factory.get_backlog(args[1])
        if not tasks:
            print("  (empty backlog)")
        for t in tasks:
            print(f"  {t['id']:10s}  [{t['priority']:8s}]  {t['title']}")

    elif cmd == "create-task":
        if len(args) < 4:
            print('Usage: create-task <project-id> "<title>" "<description>"')
            return
        task = factory.create_task(args[1], args[2], args[3])
        print(f"Created {task.id}: {task.title}")

    elif cmd == "assign":
        if len(args) < 4:
            print("Usage: assign <project-id> <task-id> <agent-id>")
            return
        factory.assign_task(args[1], args[2], args[3])
        print(f"Assigned {args[2]} to {args[3]}")

    elif cmd == "run":
        if len(args) < 3:
            print('Usage: run <agent-id> "<message>" [project-id]')
            return
        agent_id = args[1]
        message = args[2]
        project_id = args[3] if len(args) > 3 else None
        print(f"Running {agent_id}...")
        response = factory.run_agent(agent_id, message, project_id=project_id)
        print(f"\n{'─' * 60}")
        print(response)
        print(f"{'─' * 60}")

    elif cmd == "compact":
        agent_id = args[1] if len(args) > 1 else None
        results = factory.compact_memory(agent_id)
        for aid, stats in results.items():
            print(f"  {aid}: compacted={stats['compacted']}, remaining={stats['remaining']}")

    elif cmd == "templates":
        for t in factory.config.list_templates():
            print(f"  {t}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
