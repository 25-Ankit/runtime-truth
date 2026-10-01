"""Unit tests for core domain models and enums."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

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
    DeclaredModel,
    Evidence,
    Finding,
    ObservedEntity,
    ObservedModel,
    Run,
    RuntimeEvent,
    SourceLocation,
)


def test_run_model_defaults_and_serialization():
    run = Run(run_id="run_123", project_path="/path/to/project")
    assert run.run_id == "run_123"
    assert run.status == RunStatus.PENDING
    assert run.tool_version == "0.1.0"
    assert run.runtime_mode == RuntimeMode.STATIC_ONLY

    data = run.model_dump(mode="json")
    restored = Run.model_validate(data)
    assert restored.run_id == run.run_id
    assert restored.status == run.status


def test_declared_entity_validation_and_methods():
    loc = SourceLocation(file_path="requirements.txt", line_number=12, column_number=1)
    entity = DeclaredEntity(
        entity_id="ent_abc",
        run_id="run_1",
        entity_type=DeclaredEntityType.DEPENDENCY,
        name="flask",
        normalized_value="flask",
        raw_value="flask==3.0.0",
        source="requirements.txt",
        source_location=loc,
        metadata={"version": "3.0.0"},
    )
    assert entity.entity_type == DeclaredEntityType.DEPENDENCY
    assert entity.source_location.line_number == 12

    model = DeclaredModel(run_id="run_1", entities=[entity])
    assert len(model.get_by_type(DeclaredEntityType.DEPENDENCY)) == 1
    assert model.get_by_normalized_value(DeclaredEntityType.DEPENDENCY, "FLASK") is not None
    assert model.get_by_normalized_value(DeclaredEntityType.DEPENDENCY, "django") is None


def test_runtime_event_and_observed_entity():
    now = datetime.now(timezone.utc)
    ev = RuntimeEvent(
        event_id="evt_1",
        run_id="run_1",
        timestamp=now,
        pid=100,
        process="python",
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "1.2.3.4", "port": 443},
        source="strace",
        raw_reference="connect(3, ...)",
    )
    assert ev.event_type == RuntimeEventType.NETWORK_CONNECT
    assert ev.attributes["port"] == 443

    obs = ObservedEntity(
        entity_id="obs_1",
        run_id="run_1",
        entity_type=ObservedEntityType.NETWORK_DESTINATION,
        name="1.2.3.4",
        normalized_value="1.2.3.4",
        first_observed_at=now,
        last_observed_at=now,
        occurrence_count=2,
        evidence_ids=["evi_1", "evi_2"],
    )
    model = ObservedModel(run_id="run_1", entities=[obs])
    assert len(model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)) == 1


def test_evidence_and_finding_models():
    now = datetime.now(timezone.utc)
    evi = Evidence(
        evidence_id="evi_1",
        run_id="run_1",
        collector="strace",
        timestamp=now,
        description="Observed connect to 1.2.3.4:443",
        raw_evidence="connect(3, ...)",
        structured_data={"port": 443},
    )
    assert evi.collector == "strace"

    finding = Finding(
        finding_id="fnd_1",
        run_id="run_1",
        category=FindingCategory.NETWORK,
        finding_type=FindingType.NETWORK_OBSERVED_NOT_DECLARED,
        severity=FindingSeverity.HIGH,
        subject="1.2.3.4",
        explanation="Undeclared network connection",
        evidence_ids=[evi.evidence_id],
        created_at=now,
    )
    assert finding.severity == FindingSeverity.HIGH
    assert finding.evidence_ids == ["evi_1"]


def test_enum_validation_error():
    with pytest.raises(ValidationError):
        Run(run_id="r1", project_path=".", status="invalid_status")  # type: ignore

    with pytest.raises(ValidationError):
        DeclaredEntity(
            entity_id="e1",
            run_id="r1",
            entity_type="not_a_type",  # type: ignore
            name="foo",
            normalized_value="foo",
            source="test",
        )
