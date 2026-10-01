"""Configuration loader for Runtime Truth."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import tomllib
import yaml
from pydantic import BaseModel, Field


class RuntimeTruthConfig(BaseModel):
    """Configuration settings for Runtime Truth execution."""
    db_path: str = ".runtimetruth/runtimetruth.db"
    artifacts_dir: str = ".runtimetruth/runs"
    ignore_paths: List[str] = Field(
        default_factory=lambda: [
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".runtimetruth",
        ]
    )
    timeout_seconds: int = 30
    container_image: Optional[str] = None
    container_command: Optional[List[str]] = None


def load_config(project_dir: Optional[Path] = None) -> RuntimeTruthConfig:
    """Load configuration from .runtimetruth.yaml, runtimetruth.toml, or defaults."""
    base = project_dir or Path.cwd()

    yaml_candidate = base / ".runtimetruth.yaml"
    yml_candidate = base / ".runtimetruth.yml"
    toml_candidate = base / "runtimetruth.toml"

    raw_data: Dict[str, Any] = {}

    if yaml_candidate.exists():
        try:
            raw_data = yaml.safe_load(yaml_candidate.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    elif yml_candidate.exists():
        try:
            raw_data = yaml.safe_load(yml_candidate.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    elif toml_candidate.exists():
        try:
            raw_data = tomllib.loads(toml_candidate.read_text(encoding="utf-8")) or {}
        except Exception:
            pass

    return RuntimeTruthConfig.model_validate(raw_data)
