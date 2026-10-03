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
    assert data["summary"]["actionable_findings"] == 1
    assert data["summary"]["informational_observations"] == 0
    assert len(data["findings"]) == 1
    assert len(data["evidence"]) == 1

    # HTML report
    html_gen = HtmlReportGenerator()
    html_out = html_gen.generate(run, declared, observed, findings, evidence)
    assert "<!DOCTYPE html>" in html_out
    assert "run_rep" in html_out
    assert "RUNTIME_DEPENDENCY_NOT_DECLARED" in html_out
    assert "Loaded requests" in html_out
    assert "Actionable Findings" in html_out
    assert "Informational Observations" in html_out
    assert "Unresolved Correlations" in html_out


def test_finding_summary_separation():
    from datetime import datetime, timezone

    from runtime_truth.findings.engine import FindingEngine

    now = datetime.now(timezone.utc)
    engine = FindingEngine()
    findings = [
        Finding(
            finding_id="f1", run_id="r", category=FindingCategory.DEPENDENCY,
            finding_type=FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED,
            severity=FindingSeverity.LOW, subject="unused-package",
            explanation="declared not observed", created_at=now,
        ),
        Finding(
            finding_id="f2", run_id="r", category=FindingCategory.PROCESS,
            finding_type=FindingType.PROCESS_OBSERVED_NOT_DECLARED,
            severity=FindingSeverity.MEDIUM, subject="/usr/bin/echo",
            explanation="child process", evidence_ids=["e1"], created_at=now,
        ),
        Finding(
            finding_id="f3", run_id="r", category=FindingCategory.DEPENDENCY,
            finding_type=FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED,
            severity=FindingSeverity.INFO, subject="urllib3",
            explanation="package artifact", evidence_ids=["e2"], created_at=now,
        ),
        Finding(
            finding_id="f4", run_id="r", category=FindingCategory.NETWORK,
            finding_type=FindingType.NETWORK_IDENTITY_UNCORRELATED,
            severity=FindingSeverity.MEDIUM, subject="93.184.216.34",
            explanation="uncorrelated", evidence_ids=["e3"], created_at=now,
        ),
    ]
    summary = engine.summarize(findings)
    assert summary.total_findings == 4
    assert summary.actionable_findings == 2
    assert summary.informational_observations == 1
    assert summary.unresolved_correlations == 1


def test_target_process_not_emitted_but_preserved_in_observed_model():
    from datetime import datetime, timezone

    from runtime_truth.core.models import DeclaredModel, ObservedModel
    from runtime_truth.reconciliation.engine import ReconciliationEngine

    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r_tp", entities=[])
    observed = ObservedModel(
        run_id="r_tp",
        entities=[
            ObservedEntity(
                entity_id="o1", run_id="r_tp", entity_type=ObservedEntityType.PROCESS,
                name="/usr/local/bin/python3", normalized_value="/usr/local/bin/python3",
                first_observed_at=now, last_observed_at=now, occurrence_count=1,
                attributes={"is_target_process": True, "process_role": "TARGET_PROCESS"},
            ),
            ObservedEntity(
                entity_id="o2", run_id="r_tp", entity_type=ObservedEntityType.PROCESS,
                name="/usr/bin/echo", normalized_value="/usr/bin/echo",
                first_observed_at=now, last_observed_at=now, occurrence_count=1,
                attributes={"is_target_process": False, "process_role": "CHILD_PROCESS"},
            ),
        ],
    )
    findings = engine.reconcile(declared, observed)
    finding_types = {f.finding_type for f in findings}
    assert FindingType.TARGET_PROCESS not in finding_types
    assert FindingType.PROCESS_OBSERVED_NOT_DECLARED in finding_types
    # ObservedModel still retains the target process entry
    target = [e for e in observed.entities if e.attributes.get("is_target_process") is True]
    assert len(target) == 1
    assert target[0].name == "/usr/local/bin/python3"
