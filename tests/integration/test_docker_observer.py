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

    # Ensure collectors and metadata are attached (strace + stub DNS)
    collectors = {ev.collector for ev in raw_events}
    assert "strace_docker" in collectors
    assert "dns_stub" in collectors
    assert observer.last_dns_trace is not None
    assert len(observer.last_dns_trace) >= 1
    sample_ev = next(ev for ev in raw_events if ev.collector == "strace_docker")
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

        # Verify raw evidence is preserved (strace + DNS)
        assert res.raw_trace_path is not None
        assert res.raw_trace_path.exists()
        assert res.raw_trace_path.name == "strace.log"
        assert res.raw_trace_path.parent.name == "raw"
        assert len(res.raw_trace_path.read_text(encoding="utf-8")) > 0
        assert res.raw_dns_path is not None
        assert res.raw_dns_path.exists()
        assert res.raw_dns_path.name == "dns.jsonl"
        assert len(res.raw_dns_path.read_text(encoding="utf-8")) > 0

        # Verify artifacts
        assert (res.artifact_dir / "declared.json").exists()
        assert (res.artifact_dir / "events.jsonl").exists()
        assert (res.artifact_dir / "observed.json").exists()
        assert (res.artifact_dir / "findings.json").exists()
        assert (res.artifact_dir / "report.html").exists()

        # DNS resolution produced canonical events
        from runtime_truth.core.enums import RuntimeEventType

        dns_events = [e for e in res.runtime_events if e.event_type == RuntimeEventType.DNS_RESOLUTION]
        assert len(dns_events) >= 1
        a_events = [e for e in dns_events if e.attributes.get("query_type") == "A" and e.attributes.get("answers")]
        assert len(a_events) >= 1
        assert a_events[0].attributes["query_name"] == "api.example.com"
        assert "93.184.216.34" in a_events[0].attributes["answers"]

        # CASE A: declared api.example.com correlated to observed 93.184.216.34
        nets = [e for e in res.observed_model.entities if e.entity_type.value == "network_destination"]
        matched = [e for e in nets if "api.example.com" in (e.attributes.get("correlated_hostnames") or [])]
        assert len(matched) == 1

        # Check finding types: findings vs observations are separated
        finding_types = {f.finding_type for f in res.findings}
        assert FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED in finding_types
        assert FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED in finding_types
        # Correlated destination produces neither UNCORRELATED nor DECLARED_NOT_OBSERVED
        assert FindingType.NETWORK_IDENTITY_UNCORRELATED not in finding_types
        assert FindingType.NETWORK_DECLARED_NOT_OBSERVED not in finding_types
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
        assert summary.actionable_findings >= 2  # unused-package + /usr/bin/echo
        assert summary.informational_observations >= 1
        assert summary.unresolved_correlations == 0


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
