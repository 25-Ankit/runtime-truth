"""Integration tests for Docker-based runtime observation."""

import json
from pathlib import Path
import tempfile
import pytest
from typer.testing import CliRunner

from runtime_truth.cli.main import app
from runtime_truth.core.enums import FindingType, RunStatus, RuntimeMode
from runtime_truth.orchestrator import Orchestrator
from runtime_truth.runtime.observers import DockerStraceObserver
from runtime_truth.static_analysis import get_default_static_engine
from runtime_truth.storage import ArtifactExporter, Database
from tests.conftest import is_docker_available

pytestmark = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker is not available or daemon is not responsive",
)


def test_docker_observer_availability():
    observer = DockerStraceObserver()
    assert observer.is_available() is True


def test_docker_observer_ensure_image():
    observer = DockerStraceObserver()
    image = observer.ensure_tracer_image()
    assert image == "runtime-truth-tracer:latest"


def test_docker_observer_live_execution(demo_app_dir):
    observer = DockerStraceObserver()
    raw_events = observer.observe(target=demo_app_dir, run_id="integration_run_1")

    assert len(raw_events) > 0
    assert observer.last_raw_trace is not None
    assert len(observer.last_raw_trace) > 0

    # Ensure collectors and metadata are attached
    assert all(ev.collector == "strace_docker" for ev in raw_events)
    sample_ev = raw_events[0]
    assert sample_ev.metadata["image"] == "runtime-truth-tracer:latest"
    assert "exit_code" in sample_ev.metadata


def test_orchestrator_docker_mode(demo_app_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(str(Path(tmpdir) / "test_docker.db"))
        exporter = ArtifactExporter(base_dir=Path(tmpdir) / "artifacts")
        orchestrator = Orchestrator(
            db=db,
            static_engine=get_default_static_engine(),
            artifact_exporter=exporter,
        )

        res = orchestrator.execute(
            project_path=demo_app_dir,
            runtime_mode=RuntimeMode.DOCKER,
        )

        assert res.run.status == RunStatus.COMPLETED
        assert len(res.declared_model.entities) > 0
        assert len(res.observed_model.entities) > 0
        assert len(res.runtime_events) > 0
        assert len(res.findings) > 0

        # Verify raw evidence is preserved
        assert res.raw_trace_path is not None
        assert res.raw_trace_path.exists()
        assert res.raw_trace_path.name == "strace.log"
        assert res.raw_trace_path.parent.name == "raw"
        assert len(res.raw_trace_path.read_text(encoding="utf-8")) > 0

        # Verify artifacts
        assert (res.artifact_dir / "declared.json").exists()
        assert (res.artifact_dir / "events.jsonl").exists()
        assert (res.artifact_dir / "observed.json").exists()
        assert (res.artifact_dir / "findings.json").exists()
        assert (res.artifact_dir / "report.html").exists()

        # Check finding types: findings vs observations are separated
        finding_types = {f.finding_type for f in res.findings}
        assert FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED in finding_types
        assert FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED in finding_types
        assert FindingType.NETWORK_IDENTITY_UNCORRELATED in finding_types
        # TARGET_PROCESS must NOT be emitted as a finding
        assert FindingType.TARGET_PROCESS not in finding_types
        # ... but must remain in the ObservedModel
        observed_procs = [
            e for e in res.observed_model.entities if e.entity_type.value == "process"
        ]
        target_procs = [
            e
            for e in observed_procs
            if e.attributes.get("is_target_process") is True
            or e.attributes.get("process_role") == "TARGET_PROCESS"
        ]
        assert len(target_procs) >= 1
        # Child process remains an actual discrepancy
        assert FindingType.PROCESS_OBSERVED_NOT_DECLARED in finding_types
        # Summary separates actionable from informational/unresolved
        from runtime_truth.findings.engine import FindingEngine

        summary = FindingEngine().summarize(res.findings)
        assert summary.actionable_findings >= 2  # unused-package + /usr/bin/echo (+ declared network)
        assert summary.informational_observations >= 1
        assert summary.unresolved_correlations >= 1


def test_cli_scan_docker_mode(demo_app_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = str(Path(tmpdir) / "cli_docker_test.db")
        runner = CliRunner()

        scan_res = runner.invoke(
            app,
            [
                "scan",
                str(demo_app_dir),
                "--mode",
                "docker",
                "--db",
                db_file,
                "--json",
            ],
        )
        assert scan_res.exit_code == 0
        data = json.loads(scan_res.stdout)
        run_id = data["meta"]["run_id"]
        assert data["meta"]["runtime_mode"] == "docker"
        assert data["summary"]["actionable_findings"] > 0
        assert data["summary"]["informational_observations"] > 0
        assert data["summary"]["declared_entities_count"] > 0
        assert data["summary"]["observed_entities_count"] > 0
