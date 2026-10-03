"""Unit tests for reconciliation engine and finding generation."""

from datetime import datetime, timezone
import pytest

from runtime_truth.core.enums import (
    DeclaredEntityType,
    FindingCategory,
    FindingSeverity,
    FindingType,
    ObservedEntityType,
)
from runtime_truth.core.models import (
    DeclaredEntity,
    DeclaredModel,
    ObservedEntity,
    ObservedModel,
)
from runtime_truth.reconciliation.engine import ReconciliationEngine


def test_reconciliation_exact_match():
    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine()

    declared = DeclaredModel(
        run_id="r1",
        entities=[
            DeclaredEntity(
                entity_id="d1", run_id="r1", entity_type=DeclaredEntityType.DEPENDENCY,
                name="requests", normalized_value="requests", source="requirements.txt"
            ),
            DeclaredEntity(
                entity_id="d2", run_id="r1", entity_type=DeclaredEntityType.NETWORK_DESTINATION,
                name="api.example.com", normalized_value="api.example.com", source="config.json"
            ),
        ],
    )
    observed = ObservedModel(
        run_id="r1",
        entities=[
            ObservedEntity(
                entity_id="o1", run_id="r1", entity_type=ObservedEntityType.DEPENDENCY,
                name="requests", normalized_value="requests", first_observed_at=now, last_observed_at=now,
                occurrence_count=1, evidence_ids=["evi_1"]
            ),
            ObservedEntity(
                entity_id="o2", run_id="r1", entity_type=ObservedEntityType.NETWORK_DESTINATION,
                name="api.example.com", normalized_value="api.example.com", first_observed_at=now, last_observed_at=now,
                occurrence_count=1, evidence_ids=["evi_2"]
            ),
        ],
    )

    findings = engine.reconcile(declared, observed)
    assert len(findings) == 0


def test_reconciliation_discrepancies():
    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine()

    declared = DeclaredModel(
        run_id="r1",
        entities=[
            # Declared but never observed
            DeclaredEntity(
                entity_id="d1", run_id="r1", entity_type=DeclaredEntityType.DEPENDENCY,
                name="unused-pkg", normalized_value="unused-pkg", source="requirements.txt"
            ),
            # Declared network but never observed
            DeclaredEntity(
                entity_id="d2", run_id="r1", entity_type=DeclaredEntityType.NETWORK_DESTINATION,
                name="unused.example.com", normalized_value="unused.example.com", source="config.json"
            ),
        ],
    )
    observed = ObservedModel(
        run_id="r1",
        entities=[
            # Observed runtime dependency not declared
            ObservedEntity(
                entity_id="o1", run_id="r1", entity_type=ObservedEntityType.DEPENDENCY,
                name="urllib3", normalized_value="urllib3", first_observed_at=now, last_observed_at=now,
                occurrence_count=3, evidence_ids=["evi_1", "evi_2"]
            ),
            # Observed network not declared
            ObservedEntity(
                entity_id="o2", run_id="r1", entity_type=ObservedEntityType.NETWORK_DESTINATION,
                name="93.184.216.34", normalized_value="93.184.216.34", first_observed_at=now, last_observed_at=now,
                occurrence_count=1, evidence_ids=["evi_3"]
            ),
            # Observed process not declared
            ObservedEntity(
                entity_id="o3", run_id="r1", entity_type=ObservedEntityType.PROCESS,
                name="/bin/sh", normalized_value="/bin/sh", first_observed_at=now, last_observed_at=now,
                occurrence_count=1, evidence_ids=["evi_4"]
            ),
            # Observed filesystem path not declared
            ObservedEntity(
                entity_id="o4", run_id="r1", entity_type=ObservedEntityType.FILESYSTEM_PATH,
                name="/app/secret.key", normalized_value="/app/secret.key", first_observed_at=now, last_observed_at=now,
                occurrence_count=1, evidence_ids=["evi_5"]
            ),
        ],
    )

    findings = engine.reconcile(declared, observed)
    assert len(findings) == 6

    finding_types = {f.finding_type for f in findings}
    assert FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED in finding_types
    assert FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED in finding_types
    assert FindingType.NETWORK_DECLARED_NOT_OBSERVED in finding_types
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED in finding_types
    assert FindingType.PROCESS_OBSERVED_NOT_DECLARED in finding_types
    assert FindingType.FILESYSTEM_OBSERVED_NOT_DECLARED in finding_types

    # Verify evidence links
    pkg_artifact_finding = next(f for f in findings if f.finding_type == FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED)
    assert "evi_1" in pkg_artifact_finding.evidence_ids
    assert pkg_artifact_finding.severity == FindingSeverity.INFO


def test_reconciliation_stdlib_separation():
    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine()

    declared = DeclaredModel(
        run_id="r_stdlib",
        entities=[
            # Python stdlib imports
            DeclaredEntity(
                entity_id="d1", run_id="r_stdlib", entity_type=DeclaredEntityType.DEPENDENCY,
                name="json", normalized_value="json", source="app.py", metadata={"is_stdlib": True}
            ),
            DeclaredEntity(
                entity_id="d2", run_id="r_stdlib", entity_type=DeclaredEntityType.DEPENDENCY,
                name="os", normalized_value="os", source="app.py", metadata={"is_stdlib": True}
            ),
            DeclaredEntity(
                entity_id="d3", run_id="r_stdlib", entity_type=DeclaredEntityType.DEPENDENCY,
                name="pathlib", normalized_value="pathlib", source="app.py", metadata={"is_stdlib": True}
            ),
        ],
    )
    observed = ObservedModel(run_id="r_stdlib", entities=[])

    findings = engine.reconcile(declared, observed)
    # None of the stdlib imports should become third-party dependency findings
    assert len(findings) == 0


def test_reconciliation_target_process_and_workspace_activity():
    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine()

    declared = DeclaredModel(
        run_id="r_target",
        entities=[
            DeclaredEntity(
                entity_id="d_workdir", run_id="r_target", entity_type=DeclaredEntityType.FILESYSTEM_PATH,
                name="workdir", normalized_value="/app", source="Dockerfile"
            ),
            DeclaredEntity(
                entity_id="d_app", run_id="r_target", entity_type=DeclaredEntityType.DEPENDENCY,
                name="flask", normalized_value="flask", source="app.py"
            ),
            DeclaredEntity(
                entity_id="d_cfg", run_id="r_target", entity_type=DeclaredEntityType.PORT,
                name="port_8080", normalized_value="8080", source="config.json"
            ),
        ],
    )
    observed = ObservedModel(
        run_id="r_target",
        entities=[
            # Target runner process
            ObservedEntity(
                entity_id="o_proc", run_id="r_target", entity_type=ObservedEntityType.PROCESS,
                name="/usr/local/bin/python3", normalized_value="/usr/local/bin/python3",
                first_observed_at=now, last_observed_at=now, occurrence_count=1,
                attributes={"is_target_process": True, "process_role": "TARGET_PROCESS"}
            ),
            # Ordinary workspace activity: /app/app.py and /app/config.json
            ObservedEntity(
                entity_id="o_f1", run_id="r_target", entity_type=ObservedEntityType.FILESYSTEM_PATH,
                name="/app/app.py", normalized_value="/app/app.py",
                first_observed_at=now, last_observed_at=now, occurrence_count=1
            ),
            ObservedEntity(
                entity_id="o_f2", run_id="r_target", entity_type=ObservedEntityType.FILESYSTEM_PATH,
                name="/app/config.json", normalized_value="/app/config.json",
                first_observed_at=now, last_observed_at=now, occurrence_count=1
            ),
        ],
    )

    findings = engine.reconcile(declared, observed)
    finding_types = {f.finding_type for f in findings}

    # TARGET_PROCESS remains in ObservedModel but is NOT emitted as a finding
    assert FindingType.TARGET_PROCESS not in finding_types
    assert FindingType.PROCESS_OBSERVED_NOT_DECLARED not in finding_types

    # Ordinary workspace access is NOT reported as an unexplained discrepancy
    assert FindingType.FILESYSTEM_OBSERVED_NOT_DECLARED not in finding_types
    # Only the declared-but-unobserved third-party dep remains
    assert finding_types == {FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED}
