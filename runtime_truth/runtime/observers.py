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
        self.last_raw_trace: Optional[str] = None

    def is_available(self) -> bool:
        return self.log_path.exists() and self.log_path.is_file()

    def observe(self, target: Any = None, run_id: str = "") -> List[RawEvent]:
        if not self.is_available():
            raise ObservationError(f"Raw log file not found: {self.log_path}")

        raw_events: List[RawEvent] = []
        now = datetime.now(timezone.utc)
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                self.last_raw_trace = content
                for idx, line in enumerate(content.splitlines(), start=1):
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
        self.last_raw_trace: Optional[str] = None

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
            self.last_raw_trace = stderr_output
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
        self.last_raw_trace: Optional[str] = None

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

    def ensure_tracer_image(self) -> str:
        """Verify the tracer image exists or build it from Dockerfile.tracer."""
        if self.config.docker_image:
            return self.config.docker_image

        image_tag = self.config.tracer_image_tag

        # Check if image already exists locally
        inspect_res = subprocess.run(
            ["docker", "image", "inspect", image_tag],
            capture_output=True,
            timeout=5,
        )
        if inspect_res.returncode == 0:
            return image_tag

        if not self.config.build_if_missing:
            raise ObservationError(
                f"Tracer image '{image_tag}' not found and build_if_missing is False."
            )

        # Locate Dockerfile.tracer
        from runtime_truth.runtime.docker import get_tracer_dockerfile_path

        dockerfile = Path(self.config.dockerfile_path) if self.config.dockerfile_path else get_tracer_dockerfile_path()
        if not dockerfile.exists():
            raise ObservationError(f"Tracer Dockerfile not found at {dockerfile}")

        build_cmd = [
            "docker",
            "build",
            "-t",
            image_tag,
            "-f",
            str(dockerfile),
            str(dockerfile.parent),
        ]
        try:
            build_proc = subprocess.run(
                build_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if build_proc.returncode != 0:
                raise ObservationError(
                    f"Failed to build tracer image {image_tag}: {build_proc.stderr}"
                )
        except subprocess.TimeoutExpired as exc:
            raise ObservationError(f"Building tracer image timed out: {exc}") from exc
        except Exception as exc:
            raise ObservationError(f"Error building tracer image: {exc}") from exc

        return image_tag

    def build_docker_command(
        self,
        image: str,
        target_dir: Optional[Path],
        command: List[str],
    ) -> List[str]:
        """Construct the docker run command line."""
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--cap-add=SYS_PTRACE",
        ]
        if target_dir and target_dir.is_dir():
            mount_mode = "ro" if self.config.read_only_mount else "rw"
            docker_cmd.extend([
                "-v",
                f"{target_dir.resolve()}:{self.config.target_workdir}:{mount_mode}",
                "-w",
                self.config.target_workdir,
            ])

        docker_cmd.extend([
            image,
            "strace",
            "-f",
            "-tt",
            "-e",
            f"trace={','.join(self.config.syscalls)}",
            "-s",
            "1024",
            *command,
        ])
        return docker_cmd

    def observe(self, target: Any, run_id: str) -> List[RawEvent]:
        if not self.is_available():
            raise ObservationError(
                "Docker is not available or the Docker daemon is not running/accessible."
            )

        image = self.ensure_tracer_image()

        target_dir: Optional[Path] = None
        target_path = Path(str(target)) if target else None
        if target_path and target_path.exists() and target_path.is_dir():
            target_dir = target_path

        # Determine target execution command
        if self.config.container_command:
            container_cmd = list(self.config.container_command)
        elif target_dir:
            if (target_dir / "app.py").exists():
                container_cmd = ["python3", "app.py"]
            elif (target_dir / "main.py").exists():
                container_cmd = ["python3", "main.py"]
            else:
                container_cmd = ["python3", "-V"]
        else:
            container_cmd = ["python3", "-V"]

        docker_cmd = self.build_docker_command(
            image=image,
            target_dir=target_dir,
            command=container_cmd,
        )

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            stderr_output = proc.stderr
            self.last_raw_trace = stderr_output
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
                    metadata={
                        "image": image,
                        "target": str(target),
                        "run_id": run_id,
                        "exit_code": proc.returncode,
                    },
                )
            )

        return raw_events
