"""Unit tests for entity matcher."""

from datetime import datetime, timezone
from runtime_truth.core.enums import DeclaredEntityType, ObservedEntityType
from runtime_truth.core.models import DeclaredEntity, ObservedEntity
from runtime_truth.reconciliation.matcher import EntityMatcher


def test_entity_matcher_categories():
    now = datetime.now(timezone.utc)
    matcher = EntityMatcher()

    declared = [
        DeclaredEntity(
            entity_id="d1", run_id="r1", entity_type=DeclaredEntityType.DEPENDENCY,
            name="Flask", normalized_value="flask", source="requirements.txt"
        ),
        DeclaredEntity(
            entity_id="d2", run_id="r1", entity_type=DeclaredEntityType.DEPENDENCY,
            name="Unused", normalized_value="unused", source="requirements.txt"
        ),
    ]

    observed = [
        ObservedEntity(
            entity_id="o1", run_id="r1", entity_type=ObservedEntityType.DEPENDENCY,
            name="flask", normalized_value="flask", first_observed_at=now, last_observed_at=now,
            occurrence_count=1, evidence_ids=["evi_1"]
        ),
        ObservedEntity(
            entity_id="o2", run_id="r1", entity_type=ObservedEntityType.DEPENDENCY,
            name="cryptography", normalized_value="cryptography", first_observed_at=now, last_observed_at=now,
            occurrence_count=1, evidence_ids=["evi_2"]
        ),
    ]

    result = matcher.match_category(declared, observed)
    assert len(result.matched) == 1
    assert result.matched[0][0].name == "Flask"
    assert result.matched[0][1].name == "flask"

    assert len(result.declared_only) == 1
    assert result.declared_only[0].normalized_value == "unused"

    assert len(result.observed_only) == 1
    assert result.observed_only[0].normalized_value == "cryptography"
