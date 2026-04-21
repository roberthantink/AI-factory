"""
Data models for the AI Factory.

Plain dataclasses — no ORM, no database. Everything is backed by
YAML, JSON, and JSONL files on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Helpers ─────────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def next_id(prefix: str, path: Path) -> str:
    """Generate next sequential ID by counting lines in a JSONL file."""
    count = 0
    if path.exists():
        count = sum(1 for line in path.read_text().splitlines() if line.strip())
    return f"{prefix}-{count + 1:03d}"


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single JSON record as a new line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    """Read JSONL file, optionally returning only the last `limit` entries."""
    if not path.exists():
        return []
    lines = [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    if limit is not None:
        lines = lines[-limit:]
    return lines


# ── Task ────────────────────────────────────────────────────────────────────

@dataclass
class Task:
    id: str
    title: str
    description: str
    status: str = "backlog"  # backlog | active | in_review | done | blocked
    priority: str = "medium"  # low | medium | high | critical
    assigned_to: str | None = None
    created_at: str = field(default_factory=now_iso)
    created_by: str = "system"
    acceptance_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    completed_at: str | None = None
    review_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Memory entries ──────────────────────────────────────────────────────────

@dataclass
class EpisodicEntry:
    id: str
    timestamp: str
    type: str          # system | task | review | error | learning
    event: str
    summary: str
    outcome: str       # success | failure | partial | pending
    context: dict = field(default_factory=dict)
    related_task: str | None = None
    related_project: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SemanticEntry:
    id: str
    timestamp: str
    category: str      # identity | preference | domain_knowledge | pattern | constraint
    fact: str
    confidence: float = 1.0
    source: str = "agent"
    supersedes: str | None = None
    expires_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProceduralEntry:
    id: str
    timestamp: str
    category: str      # workflow | debugging | optimization | tool_usage | pattern
    procedure: str
    source: str = "agent"
    times_used: int = 0
    last_used: str | None = None
    effectiveness: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Handoff ─────────────────────────────────────────────────────────────────

@dataclass
class Handoff:
    id: str
    timestamp: str
    source_agent: str
    target_agent: str
    task_id: str
    summary: str
    context: dict = field(default_factory=dict)
    status: str = "pending"  # pending | acknowledged | completed

    def to_dict(self) -> dict:
        return asdict(self)


# ── Review ──────────────────────────────────────────────────────────────────

@dataclass
class Review:
    id: str
    timestamp: str
    task_id: str
    author_agent: str
    reviewer_agent: str
    verdict: str       # approved | rejected | changes_requested
    comments: list[dict] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
