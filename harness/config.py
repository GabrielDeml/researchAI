"""Configuration loading and canonical filesystem layout.

The repo root defaults to the parent of this package; override with the
RESEARCHAI_ROOT env var (used by tests to point at a fixture tree).
"""
from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel


class ProxyCfg(BaseModel):
    base_url: str
    api_key: str


class ModelsCfg(BaseModel):
    allowed: list[str]
    roles: dict[str, str]


class LimitsCfg(BaseModel):
    max_iterations: int = 4
    experiment_timeout_minutes: int = 30
    workspace_disk_quota_mb: int = 2048
    review_score_threshold: int = 6
    daily_max_requests: int = 0
    daily_max_tokens: int = 0
    max_parallel_projects: int = 1


class SupervisorCfg(BaseModel):
    auto_topics: bool = True
    idle_sleep_seconds: int = 300
    heartbeat_seconds: int = 30


class DashboardCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8780
    auth_token: str = ""


class Config(BaseModel):
    model_config = {"arbitrary_types_allowed": True, "ignored_types": (cached_property,)}

    proxy: ProxyCfg
    models: ModelsCfg
    limits: LimitsCfg = LimitsCfg()
    supervisor: SupervisorCfg = SupervisorCfg()
    dashboard: DashboardCfg = DashboardCfg()
    root: Path

    # --- canonical layout; all components must use these, never hardcode paths ---
    @property
    def queue_dir(self) -> Path: return self.root / "queue"
    @property
    def projects_dir(self) -> Path: return self.root / "projects"
    @property
    def journal_dir(self) -> Path: return self.root / "journal"
    @property
    def digests_dir(self) -> Path: return self.root / "digests"
    @property
    def logs_dir(self) -> Path: return self.root / "logs"
    @property
    def prompts_dir(self) -> Path: return self.root / "prompts"
    @property
    def stop_file(self) -> Path: return self.root / "STOP"
    @property
    def skip_file(self) -> Path: return self.root / "SKIP"
    @property
    def heartbeat_file(self) -> Path: return self.logs_dir / "heartbeat"
    @property
    def usage_log(self) -> Path: return self.logs_dir / "usage.jsonl"
    @property
    def supervisor_log(self) -> Path: return self.logs_dir / "supervisor.log"


def find_root() -> Path:
    env = os.environ.get("RESEARCHAI_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def load_config(root: Path | None = None) -> Config:
    root = root or find_root()
    data = yaml.safe_load((root / "config.yaml").read_text())
    data["root"] = root
    return Config.model_validate(data)
