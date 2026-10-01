"""Unit tests for reporting generators."""

from datetime import datetime, timezone
import json

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
    Evidence,
    Finding,
    ObservedEntity,
    ObservedModel,
    Run,
)
from runtime_truth.reporting import HtmlReportGenerator, JsonReportGenerator


def test_json_and_html_report_generation():
    now = datetime.now(timezone.utc)
    run = Run(run_id="run_rep", project_path="/test")
    declared = DeclaredModel(
        run_id="run_rep",
        entities=[
            DeclaredEntity(
                entity_id="d1", run_id="run_rep", entity_type=DeclaredEntityType.DEPENDENCY,
                name="flask", normalized_value="flask", source="req.txt"
            )
        ],
    )
    observed = ObservedModel(
        run_id="run_rep",
        entities=[
            ObservedEntity(
                entity_id="o1", run_id="run_rep", entity_type=ObservedEntityType.DEPENDENCY,
                name="requests", normalized_value="requests", first_observed_at=now, last_observed_at=now,
                occurrence_count=1, evidence_ids=["evi_1"]
            )
        ],
    )
    evidence = [
        Evidence(
            evidence_id="evi_1", run_id="run_rep", collector="strace",
            timestamp=now, description="Loaded requests", raw_evidence="openat(...)",
            structured_data={}
        )
    ]
    findings = [
        Finding(
            finding_id="f1", run_id="run_rep", category=FindingCategory.DEPENDENCY,
            finding_type=FindingType.RUNTIME_DEPENDENCY_NOT_DECLARED, severity=FindingSeverity.HIGH,
            subject="requests", explanation="Undeclared dep", evidence_ids=["evi_1"],
            created_at=now
        )
    ]

    # JSON report
    json_gen = JsonReportGenerator()
    json_out = json_gen.generate(run, declared, observed, findings, evidence)
    data = json.loads(json_out)
    assert data["meta"]["run_id"] == "run_rep"
    assert data["summary"]["total_findings"] == 1
    assert len(data["findings"]) == 1
    assert len(data["evidence"]) == 1

    # HTML report
    html_gen = HtmlReportGenerator()
    html_out = html_gen.generate(run, declared, observed, findings, evidence)
    assert "<!DOCTYPE html>" in html_out
    assert "run_rep" in html_out
    assert "RUNTIME_DEPENDENCY_NOT_DECLARED" in html_out
    assert "Loaded requests" in html_out
