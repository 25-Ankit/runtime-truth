"""Integration tests for orchestrator executing on demo-app fixture."""

from pathlib import Path
import tempfile

from runtime_truth.core.enums import FindingType, RunStatus, RuntimeMode
from runtime_truth.orchestrator import Orchestrator
from runtime_truth.static_analysis import get_default_static_engine
from runtime_truth.storage import ArtifactExporter, Database


def test_orchestrator_static_only(demo_app_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(str(Path(tmpdir) / "test.db"))
        exporter = ArtifactExporter(base_dir=Path(tmpdir) / "artifacts")
        orchestrator = Orchestrator(
            db=db,
            static_engine=get_default_static_engine(),
            artifact_exporter=exporter,
        )

        res = orchestrator.execute(
            project_path=demo_app_dir,
            runtime_mode=RuntimeMode.STATIC_ONLY,
        )

        assert res.run.status == RunStatus.COMPLETED
        assert len(res.declared_model.entities) > 0
        assert len(res.observed_model.entities) == 0
        assert (res.artifact_dir / "declared.json").exists()
        assert (res.artifact_dir / "report.html").exists()


def test_orchestrator_with_offline_strace_replay(demo_app_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(str(Path(tmpdir) / "test.db"))
        exporter = ArtifactExporter(base_dir=Path(tmpdir) / "artifacts")
        orchestrator = Orchestrator(
            db=db,
            static_engine=get_default_static_engine(),
            artifact_exporter=exporter,
        )

        log_file = demo_app_dir / "recorded_strace.log"
        assert log_file.exists()

        res = orchestrator.execute(
            project_path=demo_app_dir,
            runtime_mode=RuntimeMode.OFFLINE_EVENTS,
            offline_log_path=log_file,
        )

        assert res.run.status == RunStatus.COMPLETED
        assert len(res.declared_model.entities) > 0
        assert len(res.observed_model.entities) > 0
        assert len(res.runtime_events) > 0
        assert len(res.findings) > 0

        # Validate findings types
        finding_types = {f.finding_type for f in res.findings}
        assert FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED in finding_types
        assert FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED in finding_types

        # Verify artifacts
        assert (res.artifact_dir / "declared.json").exists()
        assert (res.artifact_dir / "events.jsonl").exists()
        assert (res.artifact_dir / "observed.json").exists()
        assert (res.artifact_dir / "findings.json").exists()
        assert (res.artifact_dir / "report.html").exists()


def test_orchestrator_offline_with_dns_replay_correlates(demo_app_dir):
    """Deterministic CASE A without Docker: recorded strace + recorded DNS log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(str(Path(tmpdir) / "test.db"))
        exporter = ArtifactExporter(base_dir=Path(tmpdir) / "artifacts")
        orchestrator = Orchestrator(
            db=db,
            static_engine=get_default_static_engine(),
            artifact_exporter=exporter,
        )

        log_file = demo_app_dir / "recorded_strace.log"
        dns_file = demo_app_dir / "recorded_dns.jsonl"
        assert log_file.exists()
        assert dns_file.exists()

        res = orchestrator.execute(
            project_path=demo_app_dir,
            runtime_mode=RuntimeMode.OFFLINE_EVENTS,
            offline_log_path=log_file,
            dns_log_path=dns_file,
        )

        assert res.run.status == RunStatus.COMPLETED
        assert res.raw_dns_path is not None
        assert res.raw_dns_path.name == "dns.jsonl"

        # 93.184.216.34 correlated to declared api.example.com: matched, silent.
        finding_types = {f.finding_type for f in res.findings}
        assert FindingType.NETWORK_IDENTITY_UNCORRELATED in finding_types  # 198.51.100.1 stays unresolved
        assert FindingType.NETWORK_DECLARED_NOT_OBSERVED not in finding_types
        nets = [e for e in res.observed_model.entities if e.entity_type.value == "network_destination"]
        by_ip = {e.name: e for e in nets}
        assert by_ip["93.184.216.34"].attributes["correlated_hostnames"] == ["api.example.com"]
        assert by_ip["198.51.100.1"].attributes["correlated_hostnames"] == []
