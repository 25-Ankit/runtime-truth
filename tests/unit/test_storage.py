"""Unit tests for SQLite storage layer and artifact exporter."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import pytest

from runtime_truth.core.enums import (
    DeclaredEntityType,
    FindingCategory,
    FindingSeverity,
    FindingType,
    ObservedEntityType,
    RunStatus,
    RuntimeEventType,
    RuntimeMode,
)
from runtime_truth.core.models import (
    DeclaredEntity,
    Evidence,
    Finding,
    ObservedEntity,
    Run,
    RuntimeEvent,
    SourceLocation,
)
from runtime_truth.storage import (
    ArtifactExporter,
    Database,
    DeclaredEntityRepository,
    EvidenceRepository,
    FindingRepository,
    ObservedEntityRepository,
    RunRepository,
    RuntimeEventRepository,
)


def test_storage_run_crud(memory_db):
    repo = RunRepository(memory_db)
    now = datetime.now(timezone.utc)
    run = Run(
        run_id="run_test_1",
        project_path="/test/path",
        started_at=now,
        status=RunStatus.RUNNING,
        tool_version="0.1.0",
        host_metadata={"arch": "x86_64"},
        runtime_mode=RuntimeMode.STATIC_ONLY,
    )
    repo.save(run)

    retrieved = repo.get("run_test_1")
    assert retrieved is not None
    assert retrieved.run_id == "run_test_1"
    assert retrieved.status == RunStatus.RUNNING
    assert retrieved.host_metadata["arch"] == "x86_64"

    # Update run status
    run.status = RunStatus.COMPLETED
    run.finished_at = datetime.now(timezone.utc)
    repo.save(run)

    updated = repo.get("run_test_1")
    assert updated.status == RunStatus.COMPLETED
    assert updated.finished_at is not None


def test_storage_declared_entities(memory_db):
    run_repo = RunRepository(memory_db)
    run = Run(run_id="run_d", project_path=".")
    run_repo.save(run)

    dec_repo = DeclaredEntityRepository(memory_db)
    entities = [
        DeclaredEntity(
            entity_id="e1",
            run_id="run_d",
            entity_type=DeclaredEntityType.DEPENDENCY,
            name="flask",
            normalized_value="flask",
            raw_value="flask==3.0",
            source="requirements.txt",
            source_location=SourceLocation(file_path="requirements.txt", line_number=1),
            metadata={"ver": "3.0"},
        ),
        DeclaredEntity(
            entity_id="e2",
            run_id="run_d",
            entity_type=DeclaredEntityType.PORT,
            name="port_8080",
            normalized_value="8080",
            source="Dockerfile",
            metadata={},
        ),
    ]
    dec_repo.save_many(entities)

    loaded = dec_repo.get_by_run("run_d")
    assert len(loaded) == 2
    by_name = {e.name: e for e in loaded}
    assert "flask" in by_name
    assert by_name["flask"].source_location.line_number == 1
    assert "port_8080" in by_name


def test_storage_events_and_observed(memory_db):
    run_repo = RunRepository(memory_db)
    run = Run(run_id="run_obs", project_path=".")
    run_repo.save(run)

    now = datetime.now(timezone.utc)
    event_repo = RuntimeEventRepository(memory_db)
    ev = RuntimeEvent(
        event_id="ev_1",
        run_id="run_obs",
        timestamp=now,
        pid=123,
        process="python",
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "1.1.1.1", "port": 53},
        source="strace",
        raw_reference="connect(3, ...)",
    )
    event_repo.save_many([ev])
    loaded_ev = event_repo.get_by_run("run_obs")
    assert len(loaded_ev) == 1
    assert loaded_ev[0].attributes["destination"] == "1.1.1.1"

    obs_repo = ObservedEntityRepository(memory_db)
    obs = ObservedEntity(
        entity_id="o1",
        run_id="run_obs",
        entity_type=ObservedEntityType.NETWORK_DESTINATION,
        name="1.1.1.1",
        normalized_value="1.1.1.1",
        first_observed_at=now,
        last_observed_at=now,
        occurrence_count=1,
        evidence_ids=["evi_1"],
    )
    obs_repo.save_many([obs])
    loaded_obs = obs_repo.get_by_run("run_obs")
    assert len(loaded_obs) == 1
    assert loaded_obs[0].normalized_value == "1.1.1.1"


def test_storage_evidence_and_findings(memory_db):
    run_repo = RunRepository(memory_db)
    run = Run(run_id="run_fin", project_path=".")
    run_repo.save(run)

    now = datetime.now(timezone.utc)
    evi_repo = EvidenceRepository(memory_db)
    evi = Evidence(
        evidence_id="evi_10",
        run_id="run_fin",
        collector="strace",
        timestamp=now,
        description="Syscall trace evidence",
        raw_evidence="connect(...)",
        structured_data={"port": 80},
    )
    evi_repo.save_many([evi])
    loaded_evi = evi_repo.get_by_run("run_fin")
    assert len(loaded_evi) == 1

    finding_repo = FindingRepository(memory_db)
    fnd = Finding(
        finding_id="fnd_10",
        run_id="run_fin",
        category=FindingCategory.NETWORK,
        finding_type=FindingType.NETWORK_OBSERVED_NOT_DECLARED,
        severity=FindingSeverity.HIGH,
        subject="1.1.1.1",
        explanation="Undeclared network",
        evidence_ids=["evi_10"],
        created_at=now,
    )
    finding_repo.save_many([fnd])
    loaded_fnd = finding_repo.get_by_run("run_fin")
    assert len(loaded_fnd) == 1
    assert loaded_fnd[0].finding_type == FindingType.NETWORK_OBSERVED_NOT_DECLARED


def test_artifact_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = ArtifactExporter(base_dir=Path(tmpdir))
        now = datetime.now(timezone.utc)

        declared = [
            DeclaredEntity(
                entity_id="d1", run_id="r_art", entity_type=DeclaredEntityType.DEPENDENCY,
                name="flask", normalized_value="flask", source="req.txt"
            )
        ]
        events = [
            RuntimeEvent(
                event_id="e1", run_id="r_art", timestamp=now,
                event_type=RuntimeEventType.PROCESS_SPAWN, attributes={}, source="strace"
            )
        ]
        observed = [
            ObservedEntity(
                entity_id="o1", run_id="r_art", entity_type=ObservedEntityType.PROCESS,
                name="python", normalized_value="python", first_observed_at=now, last_observed_at=now,
                occurrence_count=1
            )
        ]
        findings = [
            Finding(
                finding_id="f1", run_id="r_art", category=FindingCategory.PROCESS,
                finding_type=FindingType.PROCESS_OBSERVED_NOT_DECLARED, severity=FindingSeverity.MEDIUM,
                subject="python", explanation="Undeclared process"
            )
        ]

        run_dir = exporter.export_artifacts(
            run_id="r_art",
            declared_entities=declared,
            runtime_events=events,
            observed_entities=observed,
            findings=findings,
            html_report_content="<html><body>Test</body></html>",
        )

        assert (run_dir / "declared.json").exists()
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "observed.json").exists()
        assert (run_dir / "findings.json").exists()
        assert (run_dir / "report.html").exists()

        dec_data = json.loads((run_dir / "declared.json").read_text())
        assert len(dec_data) == 1
        assert dec_data[0]["name"] == "flask"
