"""Reconciliation engine comparing declared vs observed models to emit evidence-backed findings."""

from typing import List, Optional

from runtime_truth.core.enums import (
    DeclaredEntityType,
    FindingCategory,
    FindingSeverity,
    FindingType,
    ObservedEntityType,
)
from runtime_truth.core.models import DeclaredModel, Finding, ObservedModel
from runtime_truth.findings.engine import FindingEngine
from runtime_truth.reconciliation.matcher import EntityMatcher


class ReconciliationEngine:
    """Reconciles DeclaredModel with ObservedModel according to strict architectural contracts."""

    def __init__(
        self,
        matcher: Optional[EntityMatcher] = None,
        finding_engine: Optional[FindingEngine] = None,
    ):
        self.matcher = matcher or EntityMatcher()
        self.finding_engine = finding_engine or FindingEngine()

    def reconcile(
        self,
        declared_model: DeclaredModel,
        observed_model: ObservedModel,
    ) -> List[Finding]:
        findings: List[Finding] = []
        run_id = declared_model.run_id or observed_model.run_id

        # 1. Reconcile Dependencies
        declared_deps = declared_model.get_by_type(DeclaredEntityType.DEPENDENCY)
        observed_deps = observed_model.get_by_type(ObservedEntityType.DEPENDENCY)
        dep_match = self.matcher.match_category(declared_deps, observed_deps)

        for d in dep_match.declared_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.DEPENDENCY,
                    finding_type=FindingType.DEPENDENCY_DECLARED_NOT_OBSERVED,
                    severity=FindingSeverity.LOW,
                    subject=d.name,
                    explanation=(
                        f"Dependency '{d.name}' was declared in {d.source} "
                        f"but was not observed being imported or loaded at runtime."
                    ),
                    declared_state=d.model_dump(mode="json"),
                    observed_state=None,
                    evidence_ids=[],
                )
            )

        for o in dep_match.observed_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.DEPENDENCY,
                    finding_type=FindingType.RUNTIME_DEPENDENCY_NOT_DECLARED,
                    severity=FindingSeverity.HIGH,
                    subject=o.name,
                    explanation=(
                        f"Dependency '{o.name}' was loaded at runtime ({o.occurrence_count} access events) "
                        f"but is not declared in any dependency manifest."
                    ),
                    declared_state=None,
                    observed_state=o.model_dump(mode="json"),
                    evidence_ids=o.evidence_ids,
                )
            )

        # 2. Reconcile Network Destinations
        declared_nets = declared_model.get_by_type(DeclaredEntityType.NETWORK_DESTINATION)
        observed_nets = observed_model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
        net_match = self.matcher.match_category(declared_nets, observed_nets)

        for d in net_match.declared_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.NETWORK,
                    finding_type=FindingType.NETWORK_DECLARED_NOT_OBSERVED,
                    severity=FindingSeverity.LOW,
                    subject=d.name,
                    explanation=(
                        f"Network destination '{d.name}' was declared in {d.source} "
                        f"but no outbound network connection to it was observed."
                    ),
                    declared_state=d.model_dump(mode="json"),
                    observed_state=None,
                    evidence_ids=[],
                )
            )

        for o in net_match.observed_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.NETWORK,
                    finding_type=FindingType.NETWORK_OBSERVED_NOT_DECLARED,
                    severity=FindingSeverity.HIGH,
                    subject=o.name,
                    explanation=(
                        f"Outbound network connection to '{o.name}' was observed at runtime "
                        f"({o.occurrence_count} events) but is not declared in application configuration."
                    ),
                    declared_state=None,
                    observed_state=o.model_dump(mode="json"),
                    evidence_ids=o.evidence_ids,
                )
            )

        # 3. Reconcile Filesystem Paths
        declared_files = declared_model.get_by_type(DeclaredEntityType.FILESYSTEM_PATH)
        observed_files = observed_model.get_by_type(ObservedEntityType.FILESYSTEM_PATH)
        fs_match = self.matcher.match_category(declared_files, observed_files)

        for o in fs_match.observed_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.FILESYSTEM,
                    finding_type=FindingType.FILESYSTEM_OBSERVED_NOT_DECLARED,
                    severity=FindingSeverity.MEDIUM,
                    subject=o.name,
                    explanation=(
                        f"Application filesystem path '{o.name}' was accessed at runtime "
                        f"({o.occurrence_count} events) but not declared in volume or project configuration."
                    ),
                    declared_state=None,
                    observed_state=o.model_dump(mode="json"),
                    evidence_ids=o.evidence_ids,
                )
            )

        # 4. Reconcile Processes
        declared_procs = declared_model.get_by_type(DeclaredEntityType.PROCESS)
        observed_procs = observed_model.get_by_type(ObservedEntityType.PROCESS)
        proc_match = self.matcher.match_category(declared_procs, observed_procs)

        for o in proc_match.observed_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.PROCESS,
                    finding_type=FindingType.PROCESS_OBSERVED_NOT_DECLARED,
                    severity=FindingSeverity.MEDIUM,
                    subject=o.name,
                    explanation=(
                        f"Process '{o.name}' was spawned at runtime but not declared "
                        f"in entrypoint, CMD, or process manifests."
                    ),
                    declared_state=None,
                    observed_state=o.model_dump(mode="json"),
                    evidence_ids=o.evidence_ids,
                )
            )

        # 5. Reconcile Environment Variables
        declared_envs = declared_model.get_by_type(DeclaredEntityType.ENVIRONMENT_VARIABLE)
        observed_envs = observed_model.get_by_type(ObservedEntityType.ENVIRONMENT_VARIABLE)
        env_match = self.matcher.match_category(declared_envs, observed_envs)

        for o in env_match.observed_only:
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.ENVIRONMENT,
                    finding_type=FindingType.ENVIRONMENT_OBSERVED_NOT_DECLARED,
                    severity=FindingSeverity.LOW,
                    subject=o.name,
                    explanation=(
                        f"Environment variable '{o.name}' was accessed at runtime "
                        f"but not declared in Dockerfile ENV or project configuration."
                    ),
                    declared_state=None,
                    observed_state=o.model_dump(mode="json"),
                    evidence_ids=o.evidence_ids,
                )
            )

        return findings
