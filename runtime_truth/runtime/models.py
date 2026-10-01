"""Configuration models for runtime observation."""

from typing import List, Optional
from pydantic import BaseModel, Field


class RuntimeObserverConfig(BaseModel):
    """Configuration options for runtime observation."""
    timeout_seconds: int = 30
    follow_forks: bool = True
    syscalls: List[str] = Field(
        default_factory=lambda: [
            "execve",
            "connect",
            "openat",
            "open",
            "unlink",
            "unlinkat",
            "exit_group",
        ]
    )
    docker_image: Optional[str] = None
    container_command: Optional[List[str]] = None
    raw_log_path: Optional[str] = None
