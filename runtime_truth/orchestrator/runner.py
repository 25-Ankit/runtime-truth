"""Pipeline orchestrator executing the full static and runtime analysis flow."""

import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from runtime_truth import __version__
from runtime_truth.core.enums import RunStatus, RuntimeMode
from runtime_truth.core.identifiers import generate_run_id
from runtime_truth.core.models import (
    DeclaredModel,
    Evidence,
    Finding,
    ObservedModel,
    Run,
    RuntimeEvent,
)
from runtime_truth.observation.base import EventNormalizer, ObservedModelBuilder
from runtime_truth.observation.builder import CanonicalObservedModelBuilder
from runtime_truth.observation.normalizer import StraceEventNormalizer
from runtime_truth.reconciliation.engine import ReconciliationEngine
from runtime_truth.reporting.html_report import HtmlReportGenerator
from runtime_truth.runtime.base import RawEvent, RuntimeObserver
from runtime_truth.runtime.observers import OfflineLogObserver
from runtime_truth.static_analysis.base import StaticAnalysisEngine
from runtime_truth.storage.artifacts import ArtifactExporter
from runtime_truth.storage.database import Database
from runtime_truth.storage.repositories import (
    DeclaredEntityRepository,
    EvidenceRepository,
    FindingRepository,
    ObservedEntityRepository,
    RunRepository,
    RuntimeEventRepository,
)


@dataclass
class OrchestrationResult:
    """Complete result of an orchestration run."""
    run: Run
    declared_model: DeclaredModel
    observed_model: ObservedModel
    runtime_events: List[RuntimeEvent]
    evidence: List[Evidence]
    findings: List[Finding]
    artifact_dir: Optional[Path] = None
    html_report_path: Optional[Path] = None


class Orchestrator:
    """Coordinates static analysis, runtime observation, reconciliation, and persistence."""

    def __init__(
        self,
        db: Database,
        static_engine: StaticAnalysisEngine,
        normalizer: Optional[EventNormalizer] = None,
        model_builder: Optional[ObservedModelBuilder] = None,
        reconciliation_engine: Optional[ReconciliationEngine] = None,
        artifact_exporter: Optional[ArtifactExporter] = None,
        html_generator: Optional[HtmlReportGenerator] = None,
    ):
        self.db = db
        self.static_engine = static_engine
        self.normalizer = normalizer or StraceEventNormalizer()
        self.model_builder = model_builder or CanonicalObservedModelBuilder()
        self.reconciliation_engine = reconciliation_engine or ReconciliationEngine()
        self.artifact_exporter = artifact_exporter or ArtifactExporter()
        self.html_generator = html_generator or HtmlReportGenerator()

        # Repositories
        self.run_repo = RunRepository(db)
        self.declared_repo = DeclaredEntityRepository(db)
        self.event_repo = RuntimeEventRepository(db)
        self.observed_repo = ObservedEntityRepository(db)
        self.evidence_repo = EvidenceRepository(db)
        self.finding_repo = FindingRepository(db)

    def execute(
        self,
        project_path: Path,
        runtime_mode: RuntimeMode = RuntimeMode.STATIC_ONLY,
        observer: Optional[RuntimeObserver] = None,
        offline_log_path: Optional[Path] = None,
    ) -> OrchestrationResult:
        run_id = generate_run_id()
        resolved_project = project_path.resolve()

        host_metadata = {
            "platform": platform.platform(),
            "python_version": sys.version,
            "architecture": platform.machine(),
            "system": platform.system(),
        }

        run = Run(
            run_id=run_id,
            project_path=str(resolved_project),
            started_at=datetime.now(timezone.utc),
            status=RunStatus.RUNNING,
            tool_version=__version__,
            host_metadata=host_metadata,
            runtime_mode=runtime_mode,
        )
        self.run_repo.save(run)

        try:
            # 1. Static Analysis -> Declared Model
            declared_model = self.static_engine.scan(resolved_project, run_id=run_id)
            self.declared_repo.save_many(declared_model.entities)

            # 2. Runtime Observation -> Raw Events -> Canonical Events -> Observed Model
            runtime_events: List[RuntimeEvent] = []
            evidence_list: List[Evidence] = []
            observed_model = ObservedModel(run_id=run_id, entities=[])

            # Select observer if offline log provided
            active_observer = observer
            if offline_log_path and offline_log_path.exists():
                active_observer = OfflineLogObserver(offline_log_path)
                runtime_mode = RuntimeMode.OFFLINE_EVENTS
                run.runtime_mode = runtime_mode

            if active_observer and active_observer.is_available():
                raw_events = active_observer.observe(target=resolved_project, run_id=run_id)
                for raw_ev in raw_events:
                    canonical_ev = self.normalizer.normalize(raw_ev, run_id=run_id)
                    if canonical_ev:
                        runtime_events.append(canonical_ev)

                self.event_repo.save_many(runtime_events)
                observed_model, evidence_list = self.model_builder.build(runtime_events, run_id=run_id)
                self.observed_repo.save_many(observed_model.entities)
                self.evidence_repo.save_many(evidence_list)

            # 3. Reconciliation -> Findings
            findings = self.reconciliation_engine.reconcile(declared_model, observed_model)
            self.finding_repo.save_many(findings)

            # 4. Generate Reports & Export Artifacts
            html_content = self.html_generator.generate(
                run=run,
                declared_model=declared_model,
                observed_model=observed_model,
                findings=findings,
                evidence_list=evidence_list,
            )

            artifact_dir = self.artifact_exporter.export_artifacts(
                run_id=run_id,
                declared_entities=declared_model.entities,
                runtime_events=runtime_events,
                observed_entities=observed_model.entities,
                findings=findings,
                html_report_content=html_content,
            )

            # Complete Run
            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            self.run_repo.save(run)

            return OrchestrationResult(
                run=run,
                declared_model=declared_model,
                observed_model=observed_model,
                runtime_events=runtime_events,
                evidence=evidence_list,
                findings=findings,
                artifact_dir=artifact_dir,
                html_report_path=artifact_dir / "report.html",
            )

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            self.run_repo.save(run)
            raise exc
