"""
Configuration loader.

Reads factory.yaml, memory-tiers.yaml, agent configs, and project configs.
All paths are resolved relative to the factory root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Config:
    """Loads and holds the full factory configuration."""

    def __init__(self, factory_root: str | Path):
        self.root = Path(factory_root).resolve()
        self._factory: dict = {}
        self._tiers: dict = {}
        self._agent_cache: dict[str, dict] = {}
        self._project_cache: dict[str, dict] = {}
        self.reload()

    # ── Loading ─────────────────────────────────────────────────────────

    def reload(self) -> None:
        """(Re)load all YAML configs from disk."""
        self._factory = self._load_yaml(self.root / "config" / "factory.yaml")
        self._tiers = self._load_yaml(self.root / "config" / "memory-tiers.yaml")
        self._agent_cache.clear()
        self._project_cache.clear()

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f) or {}

    # ── Factory settings ────────────────────────────────────────────────

    @property
    def factory(self) -> dict:
        return self._factory

    @property
    def model_default(self) -> str:
        return self._factory.get("models", {}).get("default", "claude-sonnet-4-20250514")

    @property
    def model_fallback(self) -> str:
        return self._factory.get("models", {}).get("fallback", "claude-haiku-4-5-20251001")

    @property
    def max_tokens(self) -> int:
        return self._factory.get("models", {}).get("max_tokens", 8192)

    @property
    def temperature(self) -> float:
        return self._factory.get("models", {}).get("temperature", 0.3)

    @property
    def max_concurrent_agents(self) -> int:
        return self._factory.get("orchestrator", {}).get("max_concurrent_agents", 5)

    @property
    def review_required(self) -> bool:
        return self._factory.get("orchestrator", {}).get("review_required", True)

    # ── Memory tiers ────────────────────────────────────────────────────

    @property
    def tiers(self) -> dict:
        return self._tiers.get("tiers", {})

    def tier_config(self, tier: str) -> dict:
        return self.tiers.get(tier, {})

    # ── Agent configs ───────────────────────────────────────────────────

    def agent_config(self, agent_id: str) -> dict:
        if agent_id not in self._agent_cache:
            path = self.root / "agents" / agent_id / "agent.yaml"
            self._agent_cache[agent_id] = self._load_yaml(path)
        return self._agent_cache[agent_id]

    def list_agents(self) -> list[str]:
        agents_dir = self.root / "agents"
        if not agents_dir.exists():
            return []
        return sorted(
            d.name for d in agents_dir.iterdir()
            if d.is_dir() and (d / "agent.yaml").exists()
        )

    # ── Project configs ─────────────────────────────────────────────────

    def project_config(self, project_id: str) -> dict:
        if project_id not in self._project_cache:
            path = self.root / "projects" / project_id / "project.yaml"
            self._project_cache[project_id] = self._load_yaml(path)
        return self._project_cache[project_id]

    def list_projects(self) -> list[str]:
        projects_dir = self.root / "projects"
        if not projects_dir.exists():
            return []
        return sorted(
            d.name for d in projects_dir.iterdir()
            if d.is_dir() and (d / "project.yaml").exists()
        )

    # ── Agent templates ─────────────────────────────────────────────────

    def agent_template(self, role: str) -> dict:
        path = self.root / "config" / "agent-templates" / f"{role}.yaml"
        return self._load_yaml(path)

    def list_templates(self) -> list[str]:
        tpl_dir = self.root / "config" / "agent-templates"
        if not tpl_dir.exists():
            return []
        return sorted(p.stem for p in tpl_dir.glob("*.yaml"))

    # ── Path helpers ────────────────────────────────────────────────────

    def agent_dir(self, agent_id: str) -> Path:
        return self.root / "agents" / agent_id

    def project_dir(self, project_id: str) -> Path:
        return self.root / "projects" / project_id

    def workspace_dir(self, project_id: str) -> Path:
        return self.root / "projects" / project_id / "workspace"
