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
    assert FindingType.RUNTIME_DEPENDENCY_NOT_DECLARED in finding_types
    assert FindingType.NETWORK_DECLARED_NOT_OBSERVED in finding_types
    assert FindingType.NETWORK_OBSERVED_NOT_DECLARED in finding_types
    assert FindingType.PROCESS_OBSERVED_NOT_DECLARED in finding_types
    assert FindingType.FILESYSTEM_OBSERVED_NOT_DECLARED in finding_types

    # Verify evidence links
    runtime_dep_finding = next(f for f in findings if f.finding_type == FindingType.RUNTIME_DEPENDENCY_NOT_DECLARED)
    assert "evi_1" in runtime_dep_finding.evidence_ids
    assert runtime_dep_finding.severity == FindingSeverity.HIGH
