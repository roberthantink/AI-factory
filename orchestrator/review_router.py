"""
Review Router

Manages the review quality gate:
  - Routes tasks to reviewers
  - Ensures author != reviewer
  - Handles approve / reject / changes_requested flow
"""

from __future__ import annotations

from .config import Config
from .models import Review, read_jsonl, now_iso
from .memory_manager import MemoryManager
from .scheduler import Scheduler


class ReviewRouter:
    """Routes tasks through the review process."""

    def __init__(self, config: Config, memory: MemoryManager, scheduler: Scheduler):
        self.config = config
        self.memory = memory
        self.scheduler = scheduler

    def get_pending_reviews(self, project_id: str) -> list[dict]:
        path = self.config.project_dir(project_id) / "reviews" / "pending.jsonl"
        return [r for r in read_jsonl(path) if r.get("status") == "pending"]

    def assign_reviewer(self, project_id: str, review_id: str) -> str | None:
        """
        Find a reviewer for a pending review and return their agent ID.
        Returns None if no reviewer is available.
        """
        pending = self.get_pending_reviews(project_id)
        review = None
        for r in pending:
            if r["id"] == review_id:
                review = r
                break

        if review is None:
            raise ValueError(f"Review {review_id} not found in pending")

        author = review["author_agent"]
        reviewer_id = self.scheduler.find_reviewer(project_id, author)

        if reviewer_id:
            self.memory.add_timeline_event(
                project_id,
                event="review_assigned",
                summary=f"Review {review_id} for task {review['task_id']} assigned to {reviewer_id}",
                agents_involved=[reviewer_id, author],
            )

        return reviewer_id

    def submit_review(
        self,
        project_id: str,
        task_id: str,
        author_agent: str,
        reviewer_agent: str,
        verdict: str,
        comments: list[dict] | None = None,
        summary: str = "",
    ) -> Review:
        """
        Record a completed review.

        If approved, the task moves to done.
        If rejected or changes_requested, the task stays active for the author.
        """
        if reviewer_agent == author_agent:
            raise ValueError("Reviewer must be different from the author")

        if verdict not in ("approved", "rejected", "changes_requested"):
            raise ValueError(f"Invalid verdict: {verdict}")

        path = self.config.project_dir(project_id) / "reviews" / "completed.jsonl"
        from .models import next_id
        review = Review(
            id=next_id("rev", path),
            timestamp=now_iso(),
            task_id=task_id,
            author_agent=author_agent,
            reviewer_agent=reviewer_agent,
            verdict=verdict,
            comments=comments or [],
            summary=summary,
        )

        self.memory.complete_review(project_id, review)

        # Record in timeline
        self.memory.add_timeline_event(
            project_id,
            event=f"review_{verdict}",
            summary=f"Task {task_id} {verdict} by {reviewer_agent}: {summary}",
            agents_involved=[reviewer_agent, author_agent],
        )

        # If approved, complete the task
        if verdict == "approved":
            self.scheduler.complete_task(project_id, task_id)

        # Record in reviewer's episodic memory
        self.memory.add_episodic(
            reviewer_agent,
            event="review_completed",
            summary=f"Reviewed task {task_id} by {author_agent}: {verdict}",
            outcome="success",
            type_="review",
            related_task=task_id,
            related_project=project_id,
        )

        # Record in author's episodic memory
        self.memory.add_episodic(
            author_agent,
            event="review_received",
            summary=f"Task {task_id} received review from {reviewer_agent}: {verdict}. {summary}",
            outcome="success" if verdict == "approved" else "partial",
            type_="review",
            related_task=task_id,
            related_project=project_id,
        )

        return review
