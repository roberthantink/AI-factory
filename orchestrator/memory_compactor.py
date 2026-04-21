"""
Memory Compactor

Periodically summarizes old episodic memory entries to prevent
unbounded growth. Old entries get replaced with a summary entry
that preserves the key learnings without the raw detail.

This is the "intelligent forgetting" layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .models import read_jsonl, append_jsonl, now_iso


class MemoryCompactor:
    """Compacts old memory entries into summaries."""

    def __init__(self, config: Config, llm_caller=None):
        self.config = config
        self._llm_caller = llm_caller  # Optional: function(prompt) -> str

    def compact_agent_episodic(
        self,
        agent_id: str,
        max_entries: int | None = None,
        batch_size: int | None = None,
    ) -> dict:
        """
        Compact episodic memory for an agent.

        If the entry count exceeds max_entries, the oldest `batch_size`
        entries are summarized into a single entry and the originals removed.

        Returns a dict with stats: {"compacted": int, "remaining": int}
        """
        max_entries = max_entries or self.config.factory.get(
            "memory", {}
        ).get("compaction", {}).get("max_episodic_entries", 500)

        batch_size = batch_size or self.config.factory.get(
            "memory", {}
        ).get("compaction", {}).get("summary_batch_size", 50)

        path = self.config.agent_dir(agent_id) / "memory" / "episodic.jsonl"
        entries = read_jsonl(path)

        if len(entries) <= max_entries:
            return {"compacted": 0, "remaining": len(entries)}

        # Split: old entries to compact, recent entries to keep
        to_compact = entries[:batch_size]
        to_keep = entries[batch_size:]

        # Generate summary
        summary_text = self._summarize_entries(to_compact)

        # Create a summary entry
        summary_entry = {
            "id": f"ep-summary-{now_iso().replace(':', '-')}",
            "timestamp": now_iso(),
            "type": "learning",
            "event": "memory_compaction",
            "summary": summary_text,
            "context": {
                "compacted_count": len(to_compact),
                "date_range": f"{to_compact[0].get('timestamp', '?')} to {to_compact[-1].get('timestamp', '?')}",
            },
            "outcome": "success",
        }

        # Rewrite the file: summary first, then remaining entries
        all_entries = [summary_entry] + to_keep
        with open(path, "w") as f:
            for entry in all_entries:
                f.write(json.dumps(entry) + "\n")

        return {"compacted": len(to_compact), "remaining": len(all_entries)}

    def compact_all_agents(self) -> dict[str, dict]:
        """Run compaction across all agents. Returns per-agent stats."""
        results = {}
        for agent_id in self.config.list_agents():
            results[agent_id] = self.compact_agent_episodic(agent_id)
        return results

    def detect_conflicts(self, agent_id: str) -> list[dict]:
        """
        Scan semantic memory for potential contradictions.

        Simple heuristic: entries with the same category where one
        supersedes another, or entries older than the staleness threshold.

        Returns a list of potentially conflicting entry pairs.
        """
        path = self.config.agent_dir(agent_id) / "memory" / "semantic.jsonl"
        entries = read_jsonl(path)
        conflicts = []

        staleness_days = self.config.factory.get(
            "memory", {}
        ).get("conflict_resolution", {}).get("staleness_threshold_days", 30)

        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=staleness_days)

        # Group by category
        by_category: dict[str, list[dict]] = {}
        for e in entries:
            cat = e.get("category", "unknown")
            by_category.setdefault(cat, []).append(e)

        for cat, group in by_category.items():
            if len(group) < 2:
                continue
            # Flag if multiple entries in the same category with different facts
            seen_facts = set()
            for e in group:
                fact = e.get("fact", "").lower().strip()
                if fact in seen_facts:
                    continue
                for prev_fact in seen_facts:
                    # Very basic: flag if same category has multiple distinct facts
                    # A real implementation would use embedding similarity
                    conflicts.append({
                        "category": cat,
                        "fact_a": prev_fact,
                        "fact_b": fact,
                        "agent_id": agent_id,
                    })
                seen_facts.add(fact)

        return conflicts

    def _summarize_entries(self, entries: list[dict]) -> str:
        """
        Summarize a batch of episodic entries.

        If an LLM caller is available, use it. Otherwise, do a simple
        concatenation of summaries.
        """
        if self._llm_caller:
            prompt = (
                "Summarize the following agent activity log entries into a concise "
                "paragraph capturing the key events, learnings, and outcomes. "
                "Focus on what the agent learned, what worked, and what failed.\n\n"
            )
            for e in entries:
                prompt += f"- [{e.get('timestamp', '?')}] {e.get('event', '?')}: {e.get('summary', '')} → {e.get('outcome', '?')}\n"
            return self._llm_caller(prompt)

        # Fallback: simple concatenation
        summaries = [
            f"{e.get('event', '?')}: {e.get('summary', '')} ({e.get('outcome', '?')})"
            for e in entries
        ]
        return f"Compacted {len(entries)} entries: " + "; ".join(summaries)
