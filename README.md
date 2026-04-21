# AI Factory

A multi-agent programming factory with tiered memory, structured communication, and quality gates. You talk to an **Orchestrator Agent** that coordinates specialist agents (architect, backend, frontend, reviewer, QA) to get programming work done across multiple projects simultaneously.

## The Two Layers

This factory has two things called "orchestrator" — don't confuse them:

1. **The Orchestrator Agent** (`agents/orchestrator/`) — This is who you talk to. It's an AI agent with a lead-manager role. It decomposes your goals into tasks, assigns them to specialists, and coordinates the work.

2. **The Python orchestrator** (`orchestrator/`) — This is the plumbing. It's Python code that reads files, calls the Anthropic API, manages state. The Orchestrator Agent uses it as its hands.

You interact with layer 1. Layer 2 does the mechanical work in the background.

## Quick Start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key-here"

# Start a chat with the Orchestrator Agent
python cli.py chat
```

Then just talk to it:

```
you> I want to build a React Native fitness app in project-alpha. Users log workouts and see progress charts.

orchestrator> Let me break this down into tasks. First, I'll have the architect design the system.
  → [create_task] project_id=project-alpha, title=Design fitness app architecture, ...
  → [assign_task] task-002 to agent-001
  → [run_agent] agent-001 with "Start working on your assigned task"
[architect produces its design]
  → [record_decision] Use React Native with Expo, ...

The architect has proposed the system design. Shall I create implementation
tasks for the backend and frontend agents now?

you> yes, go ahead
...
```

## Architecture

```
ai-factory/
├── config/                   # Global settings and agent templates
│   ├── factory.yaml
│   ├── memory-tiers.yaml
│   └── agent-templates/      # Role definitions (orchestrator, architect, etc.)
│
├── agents/                   # Agent instances (each with its own memory)
│   ├── orchestrator/         # The lead agent — the one you chat with
│   ├── agent-001/            # Architect
│   ├── agent-002/            # Backend developer
│   └── ...                   # Add more specialists as needed
│
├── projects/                 # Project workspaces (run many at once)
│   ├── project-alpha/
│   │   ├── project.yaml
│   │   ├── memory/           # Project knowledge (decisions, timeline, facts)
│   │   ├── tasks/            # backlog.jsonl → active.jsonl → done.jsonl
│   │   ├── reviews/          # Quality gate records
│   │   ├── comms/            # Handoffs between agents
│   │   └── workspace/        # Your actual code lives here
│   │       └── .ai/          # Conventions & decisions that travel with the repo
│   └── project-beta/
│
├── shared/                   # Cross-project tools, knowledge, schemas
│
├── orchestrator/             # Python plumbing (the "hands" layer)
│   ├── main.py               # Factory class — the unified API
│   ├── llm_client.py         # Anthropic API wrapper + tool-use loop
│   ├── orchestrator_tools.py # Tools the Orchestrator Agent can call
│   ├── context_assembler.py  # Builds the tiered context window
│   ├── memory_manager.py     # Read/write agent & project memory
│   ├── memory_compactor.py   # Summarize old entries
│   ├── scheduler.py          # Task lifecycle
│   ├── review_router.py      # Review quality gate
│   └── agent_factory.py      # Create agents from templates
│
├── cli.py                    # Command-line interface (chat + direct commands)
├── requirements.txt
└── README.md
```

## How The Orchestrator Agent Works

When you chat with it, the Python layer:

1. Loads its system prompt (tells it it's the lead)
2. Assembles context (its memory + factory state)
3. Gives it a set of **tools** it can call:
   - `list_agents`, `list_projects` — survey the factory
   - `get_backlog`, `get_active_tasks` — check what's pending
   - `create_task`, `assign_task` — set up work
   - `run_agent` — execute work by calling specialist agents
   - `submit_for_review`, `record_review` — manage quality gates
   - `create_handoff`, `record_decision` — coordinate and document

4. Sends your message to the API
5. When it responds with a tool call, Python executes it and feeds the result back
6. Loops until the orchestrator gives a final text answer

You see tool calls as they happen (dimmed arrows in the chat), so the factory's work is transparent.

## Memory Model

### Per-Agent Memory (travels with the agent)

- **Episodic** (`episodic.jsonl`) — what happened: events, outcomes, errors
- **Semantic** (`semantic.jsonl`) — what I know: facts, preferences, patterns
- **Procedural** (`procedural.jsonl`) — how to do things: workflows, techniques
- **Scratchpad** (`scratchpad.md`) — current working notes

### Per-Project Memory (shared across agents on the project)

- **Decisions** (`decisions.jsonl` + `.ai/decisions.md` in the workspace) — architectural choices
- **Knowledge** (`knowledge.jsonl`) — discovered facts about the codebase/domain
- **Timeline** (`timeline.jsonl`) — audit trail
- **Conventions** (`.ai/conventions.md` in the workspace) — coding standards

### Context Tiers

| Tier | What's loaded | When |
|------|---------------|------|
| L0 | Agent identity + current task | Always |
| L1 | L0 + project conventions, decisions, agent memory | Default |
| L2 | L1 + episodic search, project knowledge, timeline | Deep work |

## Two Ways to Use the Factory

### Smart (conversational) — recommended

```bash
python cli.py chat
```

Just describe what you want. The Orchestrator Agent figures out the rest.

### Manual (direct commands) — for debugging or fine control

```bash
python cli.py status
python cli.py agents
python cli.py create-agent maya frontend-dev
python cli.py create-task project-alpha "Build login page" "React Native login screen"
python cli.py assign project-alpha task-002 maya
python cli.py run maya "Implement the login screen"
python cli.py compact
```

## Python API

If you're building something on top of the factory:

```python
from orchestrator.main import Factory

factory = Factory("/path/to/ai-factory")

# Talk to the Orchestrator Agent
reply = factory.chat_with_orchestrator("I want to add a settings screen to project-alpha")

# Or drive it manually
factory.create_agent("ada", "architect")
factory.create_task("project-alpha", "Design settings schema", "...")
factory.assign_task("project-alpha", "task-003", "ada")
response = factory.run_agent("ada", "Start working")
```

## File Format Conventions

| Format | Use for |
|--------|---------|
| YAML | Config the orchestrator parses (agent.yaml, project.yaml) |
| Markdown | Prose agents read as context (conventions.md, decisions.md) |
| JSONL | Append-only structured logs (memory, tasks, messages) |
| JSON | Single-document state (state.json, schemas) |

## Adding a New Project

1. `cp -r projects/project-alpha projects/my-project`
2. Edit `projects/my-project/project.yaml`
3. Edit `projects/my-project/workspace/.ai/conventions.md` (or let the architect populate it)
4. Wipe old data: `> projects/my-project/tasks/*.jsonl`, `> projects/my-project/memory/*.jsonl`
5. Ask the orchestrator to work on it: `python cli.py chat`

## Adding a New Agent Role

1. Add a template: `config/agent-templates/my-role.yaml`
2. Tell the orchestrator about it (or edit `agents/orchestrator/agent.yaml` to list it)
3. Create instances: `python cli.py create-agent zane my-role`

## Honest Caveats

- **The specialist agents don't yet write files directly.** They return text responses. You (or the orchestrator) act as the bridge to the workspace. Adding tool use to specialists is a natural next step.
- **Semantic search in L2 memory is not wired up.** The context assembler loads recent entries; true semantic retrieval would need embeddings. The scaffolding is there, but requires an embedding service.
- **No automatic test runs.** The QA agent writes tests but doesn't execute them. Add a test runner in `shared/tools/` and give the agent a `run_tests` tool.
- **Cost control.** Running the orchestrator uses more tokens than direct commands because of the tool-use loop. Watch your API usage.
