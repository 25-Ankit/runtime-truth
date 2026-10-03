"""Concrete runtime observer implementations."""

import json
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        self.last_dns_trace: Optional[List[Dict[str, Any]]] = None
        self.last_dns_raw: Optional[str] = None

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
        network_name: Optional[str] = None,
        dns_server: Optional[str] = None,
    ) -> List[str]:
        """Construct the docker run command line."""
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--cap-add=SYS_PTRACE",
        ]
        if network_name:
            docker_cmd.extend(["--network", network_name])
        if dns_server:
            docker_cmd.extend(["--dns", dns_server])
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

    def _load_dns_records(self, target_dir: Optional[Path]) -> Dict[str, Any]:
        """Load test-controlled DNS records from <target>/dns_records.json if present."""
        if not target_dir:
            return {}
        records_file = target_dir / self.config.dns_records_filename
        if not records_file.is_file():
            return {}
        try:
            data = json.loads(records_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ObservationError(f"Failed to parse {records_file}: {exc}") from exc
        if not isinstance(data, dict):
            raise ObservationError(f"DNS records file must contain a JSON object: {records_file}")
        return data

    def _start_dns_stub(
        self, records: Dict[str, Any], run_id: str
    ) -> Tuple[str, str, str, str]:
        """Start the stub DNS sidecar on a dedicated bridge network.

        Returns (network_name, stub_name, stub_ip, tmpdir). Raises
        ObservationError instead of degrading silently.
        """
        network_name = f"rt-dns-{uuid.uuid4().hex[:8]}"
        stub_name = f"rt-dns-stub-{uuid.uuid4().hex[:8]}"
        tmpdir = tempfile.mkdtemp(prefix="rt-dns-")
        Path(tmpdir, "records.json").write_text(json.dumps(records), encoding="utf-8")

        package_dns_dir = Path(__file__).parent / "dns"
        if not (package_dns_dir / "stub.py").is_file():
            raise ObservationError(f"DNS stub script not found in {package_dns_dir}")

        def _run(cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        try:
            proc = _run(["docker", "network", "create", network_name], timeout=30)
            if proc.returncode != 0:
                raise ObservationError(f"Failed to create docker network: {proc.stderr.strip()}")
            stub_cmd = [
                "docker", "run", "-d", "--rm",
                "--name", stub_name,
                "--network", network_name,
                "-v", f"{package_dns_dir.resolve()}:/dnsstub:ro",
                "-v", f"{tmpdir}:/dns:ro",
                self.config.dns_stub_image,
                "python", "/dnsstub/stub.py",
                "--records", "/dns/records.json",
                "--duration", str(self.config.timeout_seconds + 60),
            ]
            proc = _run(stub_cmd, timeout=120)
            if proc.returncode != 0:
                raise ObservationError(f"Failed to start DNS stub container: {proc.stderr.strip()}")
            # Resolve stub IP and wait for READY
            stub_ip = ""
            deadline = time.time() + self.config.dns_ready_timeout_seconds
            while time.time() < deadline:
                proc = _run(
                    ["docker", "inspect", "-f",
                     "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", stub_name],
                    timeout=10,
                )
                stub_ip = proc.stdout.strip()
                logs = _run(["docker", "logs", stub_name], timeout=10)
                if stub_ip and "READY" in (logs.stdout + logs.stderr):
                    return network_name, stub_name, stub_ip, tmpdir
                time.sleep(0.5)
            raise ObservationError("DNS stub container did not become ready in time")
        except Exception:
            self._stop_dns_stub(network_name, stub_name, tmpdir)
            raise

    @staticmethod
    def _stop_dns_stub(network_name: str, stub_name: str, tmpdir: str) -> None:
        try:
            subprocess.run(["docker", "rm", "-f", stub_name], capture_output=True, timeout=30)
        except Exception:
            pass
        try:
            subprocess.run(["docker", "network", "rm", network_name], capture_output=True, timeout=30)
        except Exception:
            pass
        try:
            import shutil as _shutil
            _shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def _collect_dns_raw_events(self, stub_name: str, run_id: str) -> List[Dict[str, Any]]:
        """Fetch stub stdout JSONL into last_dns_trace/last_dns_raw.

        RawEvent construction happens in observe() so sequence numbers follow
        the strace lines. Every record is preserved; nothing is discarded.
        """
        try:
            proc = subprocess.run(
                ["docker", "logs", stub_name], capture_output=True, text=True, timeout=30
            )
        except Exception as exc:
            raise ObservationError(f"Failed to collect DNS stub logs: {exc}") from exc
        raw_output = proc.stdout or ""
        self.last_dns_raw = raw_output
        records: List[Dict[str, Any]] = []
        for line in raw_output.splitlines():
            stripped = line.strip()
            if not stripped or not stripped.startswith("{"):
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or "query_name" not in rec:
                continue
            records.append(rec)
        self.last_dns_trace = records
        return records

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

        # DNS stub sidecar: deterministic in-network resolver for the run.
        # Records come from <target>/dns_records.json when present, else the
        # stub answers NXDOMAIN (honest empty observation, never fabricated).
        network_name: Optional[str] = None
        stub_name: Optional[str] = None
        stub_ip: Optional[str] = None
        tmpdir: Optional[str] = None
        dns_active = bool(self.config.dns_enabled)
        if dns_active:
            dns_records = self._load_dns_records(target_dir)
            network_name, stub_name, stub_ip, tmpdir = self._start_dns_stub(dns_records, run_id)

        docker_cmd = self.build_docker_command(
            image=image,
            target_dir=target_dir,
            command=container_cmd,
            network_name=network_name,
            dns_server=stub_ip,
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
        finally:
            if dns_active and network_name and stub_name and tmpdir:
                try:
                    self._collect_dns_raw_events(stub_name, run_id=run_id)
                finally:
                    self._stop_dns_stub(network_name, stub_name, tmpdir)

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

        if dns_active and self.last_dns_trace:
            base = len(raw_events)
            for offset, rec in enumerate(self.last_dns_trace, start=1):
                raw_events.append(
                    RawEvent(
                        sequence=base + offset,
                        collector="dns_stub",
                        raw_payload=json.dumps(rec),
                        timestamp=now,
                        metadata={"stub": stub_name, "run_id": run_id},
                    )
                )

        return raw_events
