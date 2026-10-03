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
    tracer_image_tag: str = "runtime-truth-tracer:latest"
    dockerfile_path: Optional[str] = None
    build_if_missing: bool = True
    target_workdir: str = "/app"
    read_only_mount: bool = True
    dns_enabled: bool = True
    dns_records_filename: str = "dns_records.json"
    dns_stub_image: str = "python:3.12-slim"
    dns_ready_timeout_seconds: int = 20
