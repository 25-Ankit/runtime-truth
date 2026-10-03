"""Unit tests for DockerStraceObserver and raw evidence artifact preservation."""

from pathlib import Path
import tempfile
import pytest

from runtime_truth.core.enums import (
    DeclaredEntityType,
    FindingCategory,
    FindingSeverity,
    FindingType,
    ObservedEntityType,
    RuntimeEventType,
)
from runtime_truth.core.models import (
    DeclaredEntity,
    Finding,
    ObservedEntity,
    RuntimeEvent,
)
from runtime_truth.runtime.models import RuntimeObserverConfig
from runtime_truth.runtime.observers import DockerStraceObserver
from runtime_truth.storage.artifacts import ArtifactExporter


def test_docker_observer_config_defaults():
    config = RuntimeObserverConfig()
    assert config.timeout_seconds == 30
    assert config.follow_forks is True
    assert "execve" in config.syscalls
    assert "connect" in config.syscalls
    assert config.tracer_image_tag == "runtime-truth-tracer:latest"
    assert config.target_workdir == "/app"
    assert config.read_only_mount is True
    assert config.build_if_missing is True


def test_docker_observer_command_construction_with_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir)
        (target_dir / "app.py").write_text("print('test')")

        config = RuntimeObserverConfig(
            tracer_image_tag="custom-tracer:v1",
            target_workdir="/workspace",
            read_only_mount=True,
            syscalls=["execve", "connect", "openat"],
        )
        observer = DockerStraceObserver(config=config)

        cmd = observer.build_docker_command(
            image=config.tracer_image_tag,
            target_dir=target_dir,
            command=["python3", "app.py"],
        )

        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "--cap-add=SYS_PTRACE" in cmd
        assert "-v" in cmd
        # Verify read-only mount
        mount_idx = cmd.index("-v") + 1
        assert cmd[mount_idx].endswith(":/workspace:ro")
        assert cmd[cmd.index("-w") + 1] == "/workspace"
        assert "custom-tracer:v1" in cmd
        assert "strace" in cmd
        assert "-f" in cmd
        assert "-tt" in cmd
        assert "trace=execve,connect,openat" in cmd[cmd.index("-e") + 1]
        assert cmd[-2:] == ["python3", "app.py"]


def test_docker_observer_command_construction_read_write():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir)
        config = RuntimeObserverConfig(
            read_only_mount=False,
            target_workdir="/app",
        )
        observer = DockerStraceObserver(config=config)

        cmd = observer.build_docker_command(
            image="runtime-truth-tracer:latest",
            target_dir=target_dir,
            command=["python3", "main.py"],
        )
        mount_idx = cmd.index("-v") + 1
        assert cmd[mount_idx].endswith(":/app:rw")


def test_raw_evidence_artifact_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / ".runtimetruth"
        exporter = ArtifactExporter(base_dir=base_dir)

        sample_raw_trace = "05:00:00.001 execve(\"/usr/bin/python\", ...)\n05:00:00.002 connect(3, ...) = 0\n"

        run_dir = exporter.export_artifacts(
            run_id="run_raw_test",
            declared_entities=[],
            runtime_events=[],
            observed_entities=[],
            findings=[],
            html_report_content="<html></html>",
            raw_trace_content=sample_raw_trace,
        )

        raw_file = run_dir / "raw" / "strace.log"
        assert raw_file.exists()
        assert raw_file.read_text(encoding="utf-8") == sample_raw_trace
        assert (run_dir / "declared.json").exists()
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "report.html").exists()
