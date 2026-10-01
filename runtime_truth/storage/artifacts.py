"""Filesystem artifact management for run reproducibility."""

import json
from pathlib import Path
from typing import List, Optional

from runtime_truth.core.models import (
    DeclaredEntity,
    Finding,
    ObservedEntity,
    RuntimeEvent,
)


class ArtifactExporter:
    """Exports and imports run artifacts to/from .runtimetruth/runs/<run_id>/."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(".runtimetruth")

    def get_run_dir(self, run_id: str) -> Path:
        run_dir = self.base_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def export_artifacts(
        self,
        run_id: str,
        declared_entities: List[DeclaredEntity],
        runtime_events: List[RuntimeEvent],
        observed_entities: List[ObservedEntity],
        findings: List[Finding],
        html_report_content: Optional[str] = None,
    ) -> Path:
        run_dir = self.get_run_dir(run_id)

        # 1. declared.json
        declared_file = run_dir / "declared.json"
        declared_data = [e.model_dump(mode="json") for e in declared_entities]
        declared_file.write_text(json.dumps(declared_data, indent=2), encoding="utf-8")

        # 2. events.jsonl
        events_file = run_dir / "events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            for ev in runtime_events:
                f.write(json.dumps(ev.model_dump(mode="json")) + "\n")

        # 3. observed.json
        observed_file = run_dir / "observed.json"
        observed_data = [e.model_dump(mode="json") for e in observed_entities]
        observed_file.write_text(json.dumps(observed_data, indent=2), encoding="utf-8")

        # 4. findings.json
        findings_file = run_dir / "findings.json"
        findings_data = [f.model_dump(mode="json") for f in findings]
        findings_file.write_text(json.dumps(findings_data, indent=2), encoding="utf-8")

        # 5. report.html
        if html_report_content:
            report_file = run_dir / "report.html"
            report_file.write_text(html_report_content, encoding="utf-8")

        return run_dir
