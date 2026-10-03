"""Reconciliation engine comparing declared vs observed models to emit evidence-backed findings."""

import ipaddress
from pathlib import Path
from typing import List, Optional, Set

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

        # 1. Reconcile Dependencies / Package Artifacts
        # Filter out standard-library imports (json, os, pathlib, socket, subprocess, etc.)
        # so they do not become third-party dependency findings.
        declared_deps = declared_model.get_by_type(DeclaredEntityType.DEPENDENCY)
        third_party_declared_deps = [
            d for d in declared_deps if not d.metadata.get("is_stdlib", False)
        ]

        observed_packages = (
            observed_model.get_by_type(ObservedEntityType.PACKAGE_ARTIFACT)
            + observed_model.get_by_type(ObservedEntityType.DEPENDENCY)
        )
        dep_match = self.matcher.match_category(third_party_declared_deps, observed_packages)

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
            # Reclassify site-packages runtime observations as observed package artifacts
            findings.append(
                self.finding_engine.create_finding(
                    run_id=run_id,
                    category=FindingCategory.DEPENDENCY,
                    finding_type=FindingType.PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED,
                    severity=FindingSeverity.INFO,
                    subject=o.name,
                    explanation=(
                        f"Observed package artifact '{o.name}' was accessed at runtime ({o.occurrence_count} access events) "
                        f"but is not declared in direct dependency manifests. (Direct vs transitive relationship unverified without dependency resolution)."
                    ),
                    declared_state=None,
                    observed_state=o.model_dump(mode="json"),
                    evidence_ids=o.evidence_ids,
                )
            )

        # 2. Reconcile Network Destinations (DNS-correlation aware).
        # The engine consumes normalized observations only: each observed
        # network entity carries correlated_hostnames (possibly empty) attached
        # by the ObservedModelBuilder from temporally valid dns_resolution evidence.
        # No DNS wire-format or resolver logic lives here.
        declared_nets = declared_model.get_by_type(DeclaredEntityType.NETWORK_DESTINATION)
        observed_nets = observed_model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)

        def is_ip(val: str) -> bool:
            try:
                ipaddress.ip_address(val.strip())
                return True
            except ValueError:
                return False

        declared_hostnames = [d for d in declared_nets if not is_ip(d.name)]
        declared_values = {d.normalized_value.strip().lower() for d in declared_nets}

        matched_declared_values: Set[str] = set()

        for o in observed_nets:
            correlated = sorted(o.attributes.get("correlated_hostnames") or [])
            norm_val = o.normalized_value.strip().lower()

            # Direct exact match with a declared destination (e.g. hostname to hostname or exact IP to IP)
            if norm_val in declared_values:
                matched_declared_values.add(norm_val)
                o.attributes["correlation_status"] = "MATCHED"
                continue

            if len(correlated) == 1:
                # Exactly one candidate hostname for this destination IP
                h = correlated[0]
                if h.strip().lower() in declared_values:
                    # CASE A: unambiguous match with declared destination
                    matched_declared_values.add(h.strip().lower())
                    o.attributes["correlation_status"] = "MATCHED"
                else:
                    # Unambiguous DNS identity, but NOT declared
                    o.attributes["correlation_status"] = "RESOLVED"
                    findings.append(
                        self.finding_engine.create_finding(
                            run_id=run_id,
                            category=FindingCategory.NETWORK,
                            finding_type=FindingType.NETWORK_OBSERVED_NOT_DECLARED,
                            severity=FindingSeverity.HIGH,
                            subject=h,
                            explanation=(
                                f"Outbound network connection to '{o.name}' was observed at runtime "
                                f"({o.occurrence_count} events) with DNS identity {h}, "
                                f"which is not declared in application configuration."
                            ),
                            declared_state=None,
                            observed_state=o.model_dump(mode="json"),
                            evidence_ids=o.evidence_ids,
                        )
                    )

            elif len(correlated) > 1:
                # SHARED-IP AMBIGUITY: Multiple observed hostnames share this destination IP.
                # Do NOT claim any declared hostname was matched unless evidence distinguishes it.
                # Do NOT call this "undeclared".
                o.attributes["correlation_status"] = "AMBIGUOUS"
                o.attributes["correlation_reason"] = "Multiple observed hostnames share destination IP"
                findings.append(
                    self.finding_engine.create_finding(
                        run_id=run_id,
                        category=FindingCategory.NETWORK,
                        finding_type=FindingType.NETWORK_IDENTITY_AMBIGUOUS,
                        severity=FindingSeverity.MEDIUM,
                        subject=o.name,
                        explanation=(
                            f"Observed outbound connection to destination IP '{o.name}' "
                            f"has multiple candidate hostnames ({', '.join(correlated)}) "
                            f"sharing the destination IP and cannot be disambiguated without additional evidence."
                        ),
                        declared_state=None,
                        observed_state=o.model_dump(mode="json"),
                        evidence_ids=o.evidence_ids,
                    )
                )

            else:
                # len(correlated) == 0: UNRESOLVED (no valid DNS resolution observed)
                o.attributes["correlation_status"] = "UNRESOLVED"
                if is_ip(o.name) and declared_hostnames:
                    # CASE C: numeric IP with declared hostname(s) but no DNS
                    # evidence mapping them. Do not call it definitely undeclared.
                    findings.append(
                        self.finding_engine.create_finding(
                            run_id=run_id,
                            category=FindingCategory.NETWORK,
                            finding_type=FindingType.NETWORK_IDENTITY_UNCORRELATED,
                            severity=FindingSeverity.MEDIUM,
                            subject=o.name,
                            explanation=(
                                f"Observed outbound connection to numeric IP '{o.name}' "
                                f"({o.occurrence_count} events) cannot be correlated with declared hostname(s) "
                                f"({', '.join(d.name for d in declared_hostnames)}) without DNS evidence."
                            ),
                            declared_state=None,
                            observed_state=o.model_dump(mode="json"),
                            evidence_ids=o.evidence_ids,
                        )
                    )
                else:
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

        # Reconcile declared network destinations that were not matched
        for d in declared_nets:
            if d.normalized_value.strip().lower() not in matched_declared_values:
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

        # 3. Reconcile Filesystem Paths
        declared_files = declared_model.get_by_type(DeclaredEntityType.FILESYSTEM_PATH)
        observed_files = observed_model.get_by_type(ObservedEntityType.FILESYSTEM_PATH)
        fs_match = self.matcher.match_category(declared_files, observed_files)

        # Collect project source and manifest files to identify ordinary target-workspace activity
        project_sources: Set[str] = {Path(e.source).name for e in declared_model.entities if e.source}

        def is_expected_workspace_activity(fpath: str) -> bool:
            norm = fpath.strip().rstrip("/")
            p = Path(norm)
            # Check declared filesystem paths (e.g. WORKDIR /app or /app)
            for d in declared_files:
                d_val = d.normalized_value.strip().rstrip("/")
                if norm == d_val:
                    return True
                if norm.startswith(f"{d_val}/"):
                    if p.name in project_sources or norm == f"{d_val}":
                        return True
            # Check standard workspace directory paths (/app/app.py, /app/config.json, etc.)
            if (norm.startswith("/app/") or norm == "/app") and p.name in project_sources:
                return True
            return False

        for o in fs_match.observed_only:
            if is_expected_workspace_activity(o.name):
                # Ordinary target-workspace access; expected runtime workspace activity
                continue

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
            is_target_proc = (
                o.attributes.get("is_target_process", False)
                or o.attributes.get("process_role") == "TARGET_PROCESS"
            )
            if is_target_proc:
                # TARGET_PROCESS remains part of the ObservedModel/runtime summary
                # but is NOT emitted as a reconciliation finding.
                continue
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
