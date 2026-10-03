"""Engine for generating deterministic findings from reconciliation discrepancies."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from runtime_truth.core.enums import (
    FindingCategory,
    FindingSeverity,
    FindingType,
)
from runtime_truth.core.identifiers import generate_finding_id
from runtime_truth.core.models import Finding
from runtime_truth.findings.models import FindingSummary


ACTIONABLE_FINDING_TYPES = frozenset(
    {
        FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED,
        FindingType.RUNTIME_DEPENDENCY_NOT_DECLARED,
        FindingType.NETWORK_DECLARED_NOT_OBSERVED,
        FindingType.NETWORK_OBSERVED_NOT_DECLARED,
        FindingType.FILESYSTEM_OBSERVED_NOT_DECLARED,
        FindingType.PROCESS_OBSERVED_NOT_DECLARED,
        FindingType.ENVIRONMENT_OBSERVED_NOT_DECLARED,
        FindingType.BEHAVIORAL_DRIFT,
    }
)

INFORMATIONAL_OBSERVATION_TYPES = frozenset(
    {
        FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED,
        FindingType.TARGET_PROCESS,
    }
)

UNRESOLVED_CORRELATION_TYPES = frozenset(
    {
        FindingType.NETWORK_IDENTITY_UNCORRELATED,
    }
)


class FindingEngine:
    """Creates structured, evidence-backed findings."""

    def create_finding(
        self,
        run_id: str,
        category: FindingCategory,
        finding_type: FindingType,
        severity: FindingSeverity,
        subject: str,
        explanation: str,
        declared_state: Optional[Dict[str, Any]] = None,
        observed_state: Optional[Dict[str, Any]] = None,
        evidence_ids: Optional[List[str]] = None,
    ) -> Finding:
        finding_id = generate_finding_id(run_id, finding_type.value, subject)
        return Finding(
            finding_id=finding_id,
            run_id=run_id,
            category=category,
            finding_type=finding_type,
            severity=severity,
            subject=subject,
            declared_state=declared_state,
            observed_state=observed_state,
            explanation=explanation,
            evidence_ids=evidence_ids or [],
            created_at=datetime.now(timezone.utc),
        )

    def summarize(self, findings: List[Finding]) -> FindingSummary:
        summary = FindingSummary(total_findings=len(findings))
        for f in findings:
            summary.by_category[f.category] = summary.by_category.get(f.category, 0) + 1
            summary.by_severity[f.severity] = summary.by_severity.get(f.severity, 0) + 1
            summary.by_type[f.finding_type] = summary.by_type.get(f.finding_type, 0) + 1
            if f.finding_type in UNRESOLVED_CORRELATION_TYPES:
                summary.unresolved_correlations += 1
            elif f.finding_type in INFORMATIONAL_OBSERVATION_TYPES:
                summary.informational_observations += 1
            else:
                summary.actionable_findings += 1
        return summary
