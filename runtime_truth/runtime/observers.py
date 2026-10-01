"""Concrete runtime observer implementations."""

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from runtime_truth.core.errors import ObservationError
from runtime_truth.runtime.base import RawEvent, RuntimeObserver
from runtime_truth.runtime.models import RuntimeObserverConfig


class OfflineLogObserver(RuntimeObserver):
    """Replays raw strace or collector logs from a file.
    
    Ensures deterministic testing and reproducibility without needing live root or containers.
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)

    def is_available(self) -> bool:
        return self.log_path.exists() and self.log_path.is_file()

    def observe(self, target: Any = None, run_id: str = "") -> List[RawEvent]:
        if not self.is_available():
            raise ObservationError(f"Raw log file not found: {self.log_path}")

        raw_events: List[RawEvent] = []
        now = datetime.now(timezone.utc)
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    raw_events.append(
                        RawEvent(
                            sequence=idx,
                            collector="strace_offline",
                            raw_payload=stripped,
                            timestamp=now,
                            metadata={"file": str(self.log_path), "line": idx},
                        )
                    )
        except Exception as exc:
            raise ObservationError(f"Failed to read offline log file: {exc}") from exc

        return raw_events


class StraceHostObserver(RuntimeObserver):
    """Executes a target command on the host traced by strace."""

    def __init__(self, config: Optional[RuntimeObserverConfig] = None):
        self.config = config or RuntimeObserverConfig()

    def is_available(self) -> bool:
        return shutil.which("strace") is not None

    def observe(self, target: Any, run_id: str) -> List[RawEvent]:
        if not self.is_available():
            raise ObservationError(
                "strace is not installed on the host system. "
                "Install strace or use DockerStraceObserver / OfflineLogObserver."
            )

        command = target if isinstance(target, list) else [str(target)]
        strace_cmd = [
            "strace",
            "-f",  # follow child processes
            "-tt",  # microsecond timestamps
            "-e",
            f"trace={','.join(self.config.syscalls)}",
            "-s",
            "1024",  # capture string arguments up to 1024 bytes
            *command,
        ]

        try:
            proc = subprocess.run(
                strace_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            stderr_output = proc.stderr
        except subprocess.TimeoutExpired as exc:
            raise ObservationError(f"Execution timed out after {self.config.timeout_seconds}s") from exc
        except Exception as exc:
            raise ObservationError(f"Failed to execute strace: {exc}") from exc

        raw_events: List[RawEvent] = []
        now = datetime.now(timezone.utc)
        for idx, line in enumerate(stderr_output.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            raw_events.append(
                RawEvent(
                    sequence=idx,
                    collector="strace_host",
                    raw_payload=stripped,
                    timestamp=now,
                    metadata={"exit_code": proc.returncode},
                )
            )

        return raw_events


class DockerStraceObserver(RuntimeObserver):
    """Executes a containerized target with strace inside a Docker container."""

    def __init__(self, config: Optional[RuntimeObserverConfig] = None):
        self.config = config or RuntimeObserverConfig()

    def is_available(self) -> bool:
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            # Check docker daemon connectivity non-interactively
            res = subprocess.run(["docker", "info"], capture_output=True, timeout=3)
            return res.returncode == 0
        except Exception:
            return False

    def observe(self, target: Any, run_id: str) -> List[RawEvent]:
        if not self.is_available():
            raise ObservationError(
                "Docker is not available or the Docker daemon is not running/accessible."
            )

        image = self.config.docker_image or (str(target) if isinstance(target, str) else "python:3.12-slim")
        container_cmd = self.config.container_command or ["python", "app.py"]

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--cap-add=SYS_PTRACE",
            image,
            "strace",
            "-f",
            "-tt",
            "-e",
            f"trace={','.join(self.config.syscalls)}",
            "-s",
            "1024",
            *container_cmd,
        ]

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            stderr_output = proc.stderr
        except subprocess.TimeoutExpired as exc:
            raise ObservationError(f"Docker execution timed out after {self.config.timeout_seconds}s") from exc
        except Exception as exc:
            raise ObservationError(f"Failed to execute Docker container with strace: {exc}") from exc

        raw_events: List[RawEvent] = []
        now = datetime.now(timezone.utc)
        for idx, line in enumerate(stderr_output.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            raw_events.append(
                RawEvent(
                    sequence=idx,
                    collector="strace_docker",
                    raw_payload=stripped,
                    timestamp=now,
                    metadata={"image": image, "exit_code": proc.returncode},
                )
            )

        return raw_events
