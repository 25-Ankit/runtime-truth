"""JSON report generator."""

import json
from typing import List, Optional

from runtime_truth.core.models import (
    DeclaredModel,
    Evidence,
    Finding,
    ObservedModel,
    Run,
)
from runtime_truth.findings.engine import FindingEngine


class JsonReportGenerator:
    """Produces structured JSON reports."""

    def __init__(self, finding_engine: Optional[FindingEngine] = None):
        self.finding_engine = finding_engine or FindingEngine()

    def generate(
        self,
        run: Run,
        declared_model: DeclaredModel,
        observed_model: ObservedModel,
        findings: List[Finding],
        evidence_list: List[Evidence],
        indent: int = 2,
    ) -> str:
        summary = self.finding_engine.summarize(findings)

        report_dict = {
            "meta": {
                "tool": "Runtime Truth",
                "version": run.tool_version,
                "run_id": run.run_id,
                "project_path": run.project_path,
                "status": run.status.value,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "runtime_mode": run.runtime_mode.value,
                "host_metadata": run.host_metadata,
            },
            "summary": {
                "total_findings": summary.total_findings,
                "actionable_findings": summary.actionable_findings,
                "informational_observations": summary.informational_observations,
                "unresolved_correlations": summary.unresolved_correlations,
                "by_category": {k.value: v for k, v in summary.by_category.items()},
                "by_severity": {k.value: v for k, v in summary.by_severity.items()},
                "by_type": {k.value: v for k, v in summary.by_type.items()},
                "declared_entities_count": len(declared_model.entities),
                "observed_entities_count": len(observed_model.entities),
            },
            "findings": [f.model_dump(mode="json") for f in findings],
            "declared_model": declared_model.model_dump(mode="json"),
            "observed_model": observed_model.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in evidence_list],
        }

        return json.dumps(report_dict, indent=indent)
