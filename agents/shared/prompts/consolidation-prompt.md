# Session Consolidation Protocol — Athena Role

You are **Athena** (Reviewer). Run this at the end of every session.

## Goal

Convert recent episodic entries (what happened) into durable procedural rules (how to do it better), for every agent that had activity this session.

## Steps

### 1. Identify active agents

List which agents produced work this session (check which `episodic.jsonl` files were written to during this session).

### 2. Per agent: read and analyze

For each active agent, read `agents/<agent>/memory/episodic.jsonl`.

Focus on entries since the previous consolidation (most recent entries first). Look for:
- **Repeated mistakes**: the same type of error appearing in 2+ entries → strong candidate for a "never do X" rule
- **Repeated successes**: the same approach working 2+ times → strong candidate for a "when X, always Y" rule
- **Non-obvious findings**: one-off discoveries that a future agent would need to know → candidate for a semantic entry instead

### 3. Per agent: check existing procedural memory

Read `agents/<agent>/memory/procedural.jsonl`.

**Skip** writing a new rule if:
- The pattern is already covered (even loosely)
- The pattern appeared only once in episodic history
- The pattern is too task-specific to generalize

### 4. Per agent: write new procedural rules

If a pattern qualifies, append to `agents/<agent>/memory/procedural.jsonl`:

```json
{
  "id": "proc-XXX",
  "timestamp": "<ISO 8601 now>",
  "category": "workflow | debugging | optimization | tool_usage | pattern",
  "procedure": "Actionable rule starting with a condition. E.g.: 'When building X in React Native Web, always Y because Z.'",
  "source": "consolidation-<YYYY-MM-DD>",
  "times_used": 0,
  "last_used": null,
  "effectiveness": null
}
```

- Increment `proc-XXX` from the highest existing id in that file.
- Keep `procedure` dense and actionable. One rule = one file write. No vague rules.
- Category guide: `workflow` = process steps; `debugging` = error diagnosis; `optimization` = performance; `tool_usage` = specific tool/API patterns; `pattern` = code/design patterns.

### 5. Handle cross-agent findings

If you find a pattern in one agent's work that clearly applies to another agent too (e.g., a React Native Web quirk found by Apollo that Hephaestus should also know), write the rule to **both** agents' procedural files — adapt the wording to the receiving agent's domain.

### 6. Log the consolidation run

Append to `agents/athena/memory/episodic.jsonl`:

```json
{
  "id": "ep-XXX",
  "timestamp": "<ISO 8601 now>",
  "type": "learning",
  "event": "session-consolidation",
  "summary": "Consolidated session. Agents reviewed: [list]. New rules written: N. Cross-agent rules: N.",
  "context": { "agents_reviewed": [...], "rules_added": N },
  "outcome": "success",
  "related_task": null,
  "related_project": null
}
```

### 7. Done

Return to Prometheus role. The Stop hook will commit and push everything to GitHub automatically.
