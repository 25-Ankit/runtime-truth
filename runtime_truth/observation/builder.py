"""Builds ObservedModel and supporting Evidence records from canonical RuntimeEvents."""

import ipaddress
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from runtime_truth.core.enums import ObservedEntityType, RuntimeEventType
from runtime_truth.core.identifiers import generate_entity_id, generate_evidence_id
from runtime_truth.core.models import Evidence, ObservedEntity, ObservedModel, RuntimeEvent
from runtime_truth.observation.base import ObservedModelBuilder
from runtime_truth.observation.dns import (
    DEFAULT_CORRELATION_WINDOW_SECONDS,
    as_utc,
    build_dns_identity_table,
    extract_dns_identity,
)


def _is_local_infrastructure(dest: str) -> bool:
    """Loopback and unspecified addresses are resolver/container plumbing.

    Covers 127.0.0.1, Docker's embedded DNS endpoint 127.0.0.11, ::1 and
    0.0.0.0. DNS evidence for real lookups is still recorded by the stub
    observer; only the plumbing connection itself is suppressed here.
    """
    try:
        addr = ipaddress.ip_address(dest.strip())
    except ValueError:
        return False
    return addr.is_loopback or addr.is_unspecified


class CanonicalObservedModelBuilder(ObservedModelBuilder):
    """Synthesizes ObservedEntity records and Evidence from normalized RuntimeEvents."""

    # Patterns to extract package names from file access paths
    PYTHON_PKG_REGEX = re.compile(
        r"(?:site-packages|dist-packages)/([a-zA-Z0-9_\-\.]+)"
    )
    NODE_PKG_REGEX = re.compile(
        r"node_modules/([a-zA-Z0-9_\-\.]+)"
    )

    # Standard system paths to ignore for application filesystem discrepancies
    IGNORED_SYS_PATH_PREFIXES = (
        "/proc/",
        "/sys/",
        "/dev/",
        "/lib/",
        "/lib64/",
        "/usr/",
        "/etc/",
        "/bin/",
        "/sbin/",
    )

    def _extract_dependency(self, path: str) -> Optional[str]:
        py_match = self.PYTHON_PKG_REGEX.search(path)
        if py_match:
            pkg = py_match.group(1)
            # Filter out .dist-info or .egg-info suffix if present
            if ".dist-info" in pkg or ".egg-info" in pkg:
                pkg = pkg.split(".")[0]
            if pkg.endswith(".py"):
                pkg = pkg[:-3]
            return pkg.lower().replace("_", "-")

        node_match = self.NODE_PKG_REGEX.search(path)
        if node_match:
            return node_match.group(1).lower()

        return None

    DEFAULT_CORRELATION_WINDOW_SECONDS: float = 60.0
    DEFAULT_TIME_SKEW_TOLERANCE_SECONDS: float = 0.5

    def __init__(
        self,
        correlation_window_seconds: float = DEFAULT_CORRELATION_WINDOW_SECONDS,
        time_skew_tolerance: float = DEFAULT_TIME_SKEW_TOLERANCE_SECONDS,
    ):
        self.correlation_window_seconds = correlation_window_seconds
        self.time_skew_tolerance = time_skew_tolerance

    def build(self, events: List[RuntimeEvent], run_id: str) -> Tuple[ObservedModel, List[Evidence]]:
        observed_map: Dict[str, ObservedEntity] = {}
        all_evidence: List[Evidence] = []
        target_process_identified = False

        # Pass 1: evidence for every event + DNS identity collection.
        # Identity is resolved run-scoped (all successful resolutions in this
        # run may justify correlation), so entity synthesis in pass 2 sees the
        # complete table regardless of event order.
        evidence_by_event: Dict[str, str] = {}
        dns_events: List[RuntimeEvent] = []
        for ev in events:
            # Generate Evidence record for the event
            description = ""
            if ev.event_type == RuntimeEventType.NETWORK_CONNECT:
                dest = ev.attributes.get("destination", "unknown")
                port = ev.attributes.get("port", "")
                description = f"Observed network connection to {dest}:{port}"
            elif ev.event_type == RuntimeEventType.DNS_RESOLUTION:
                qname = ev.attributes.get("query_name", "unknown")
                qtype = ev.attributes.get("query_type", "?")
                answers = ev.attributes.get("answers") or []
                rcode = ev.attributes.get("rcode", "UNKNOWN")
                if answers:
                    description = (
                        f"Observed DNS resolution {qname} ({qtype}) -> "
                        f"{', '.join(answers)} [{rcode}]"
                    )
                else:
                    description = f"Observed DNS query {qname} ({qtype}) failed [{rcode}]"
                dns_events.append(ev)
            elif ev.event_type in (RuntimeEventType.FILE_READ, RuntimeEventType.FILE_WRITE, RuntimeEventType.FILE_CREATE, RuntimeEventType.FILE_DELETE):
                fpath = ev.attributes.get("path", "unknown")
                description = f"Observed {ev.event_type.value} on {fpath}"
            elif ev.event_type == RuntimeEventType.PROCESS_SPAWN:
                exe = ev.attributes.get("executable", "unknown")
                description = f"Observed process spawn of {exe}"
            elif ev.event_type == RuntimeEventType.PROCESS_EXIT:
                description = f"Observed process exit with code {ev.attributes.get('exit_code', 0)}"
            else:
                description = f"Observed {ev.event_type.value}"

            evidence_id = generate_evidence_id(run_id, ev.source, f"{ev.event_id}_{len(all_evidence)}")
            evidence = Evidence(
                evidence_id=evidence_id,
                run_id=run_id,
                event_id=ev.event_id,
                collector=ev.source,
                timestamp=ev.timestamp,
                description=description,
                raw_evidence=ev.raw_reference,
                structured_data=ev.attributes,
            )
            all_evidence.append(evidence)
            evidence_by_event[ev.event_id] = evidence_id

        ip_to_names, _ = build_dns_identity_table(dns_events)
        dns_evidence_by_ip: Dict[str, List[str]] = {}
        for dev in dns_events:
            identity = extract_dns_identity(dev)
            if identity is None:
                continue
            dev_evi = evidence_by_event.get(dev.event_id)
            if dev_evi is None:
                continue
            for ip in identity[1]:
                if dev_evi not in dns_evidence_by_ip.setdefault(ip, []):
                    dns_evidence_by_ip[ip].append(dev_evi)

        # Pass 2: entity synthesis. Network entities gain correlated_hostnames
        # plus the DNS evidence ids supporting the correlation, validated
        # through the deterministic temporal correlation window.
        for ev in events:
            evidence_id = evidence_by_event.get(ev.event_id)
            if evidence_id is None:
                continue
            # Map to ObservedEntity
            # 1. Network Connect
            if ev.event_type == RuntimeEventType.NETWORK_CONNECT:
                dest = ev.attributes.get("destination")
                if dest and not _is_local_infrastructure(dest):
                    norm_dest = dest.lower()
                    key = f"network:{norm_dest}"
                    conn_ts = as_utc(ev.timestamp)

                    # Temporal correlation: find all successful DNS resolutions
                    # for this IP that occurred prior to or at connection time
                    # within the correlation window:
                    # 0.0 <= (conn_time - dns_time) <= correlation_window_seconds
                    valid_candidates: Set[str] = set()
                    valid_dns_evidence: List[str] = []
                    for dev in dns_events:
                        identity = extract_dns_identity(dev)
                        if identity is None:
                            continue
                        qname, answers = identity
                        answers_norm = {a.strip().lower() for a in answers}
                        if norm_dest in answers_norm or dest.strip().lower() in answers_norm:
                            dns_ts = as_utc(dev.timestamp)
                            elapsed = (conn_ts - dns_ts).total_seconds()
                            if -self.time_skew_tolerance <= elapsed <= self.correlation_window_seconds:
                                valid_candidates.add(qname)
                                dev_evi = evidence_by_event.get(dev.event_id)
                                if dev_evi and dev_evi not in valid_dns_evidence:
                                    valid_dns_evidence.append(dev_evi)

                    correlated = sorted(valid_candidates)
                    net_attrs = dict(ev.attributes)
                    net_attrs["correlated_hostnames"] = correlated

                    if len(correlated) > 1:
                        net_attrs["correlation_status"] = "AMBIGUOUS"
                        net_attrs["correlation_reason"] = "Multiple observed hostnames share destination IP"
                    elif len(correlated) == 1:
                        net_attrs["correlation_status"] = "RESOLVED"
                    else:
                        net_attrs["correlation_status"] = "UNRESOLVED"

                    if key in observed_map:
                        ent = observed_map[key]
                        ent.last_observed_at = ev.timestamp
                        ent.occurrence_count += 1
                        ent.evidence_ids.append(evidence_id)
                        for dev_evi in valid_dns_evidence:
                            if dev_evi not in ent.evidence_ids:
                                ent.evidence_ids.append(dev_evi)
                        merged = set(ent.attributes.get("correlated_hostnames", [])) | valid_candidates
                        merged_sorted = sorted(merged)
                        ent.attributes["correlated_hostnames"] = merged_sorted
                        if len(merged_sorted) > 1:
                            ent.attributes["correlation_status"] = "AMBIGUOUS"
                            ent.attributes["correlation_reason"] = "Multiple observed hostnames share destination IP"
                        elif len(merged_sorted) == 1:
                            ent.attributes["correlation_status"] = "RESOLVED"
                        else:
                            ent.attributes["correlation_status"] = "UNRESOLVED"
                    else:
                        ent_id = generate_entity_id(ObservedEntityType.NETWORK_DESTINATION.value, norm_dest)
                        evidence_ids = [evidence_id]
                        for dev_evi in valid_dns_evidence:
                            if dev_evi not in evidence_ids:
                                evidence_ids.append(dev_evi)
                        observed_map[key] = ObservedEntity(
                            entity_id=ent_id,
                            run_id=run_id,
                            entity_type=ObservedEntityType.NETWORK_DESTINATION,
                            name=dest,
                            normalized_value=norm_dest,
                            first_observed_at=ev.timestamp,
                            last_observed_at=ev.timestamp,
                            occurrence_count=1,
                            evidence_ids=evidence_ids,
                            attributes=net_attrs,
                        )

            # 2. File Read / Write -> Check for runtime dependencies
            elif ev.event_type in (RuntimeEventType.FILE_READ, RuntimeEventType.FILE_WRITE):
                fpath = ev.attributes.get("path")
                if fpath:
                    # Check dependency / package artifact
                    dep_name = self._extract_dependency(fpath)
                    if dep_name:
                        key = f"package_artifact:{dep_name}"
                        if key in observed_map:
                            ent = observed_map[key]
                            ent.last_observed_at = ev.timestamp
                            ent.occurrence_count += 1
                            ent.evidence_ids.append(evidence_id)
                        else:
                            ent_id = generate_entity_id(ObservedEntityType.PACKAGE_ARTIFACT.value, dep_name)
                            observed_map[key] = ObservedEntity(
                                entity_id=ent_id,
                                run_id=run_id,
                                entity_type=ObservedEntityType.PACKAGE_ARTIFACT,
                                name=dep_name,
                                normalized_value=dep_name,
                                first_observed_at=ev.timestamp,
                                last_observed_at=ev.timestamp,
                                occurrence_count=1,
                                evidence_ids=[evidence_id],
                                attributes={
                                    "sample_path": fpath,
                                    "observation_type": "observed_package_artifact",
                                },
                            )

                    # Also track non-system application file access
                    if not any(fpath.startswith(prefix) for prefix in self.IGNORED_SYS_PATH_PREFIXES) and not dep_name:
                        key = f"filesystem:{fpath}"
                        if key in observed_map:
                            ent = observed_map[key]
                            ent.last_observed_at = ev.timestamp
                            ent.occurrence_count += 1
                            ent.evidence_ids.append(evidence_id)
                        else:
                            ent_id = generate_entity_id(ObservedEntityType.FILESYSTEM_PATH.value, fpath)
                            observed_map[key] = ObservedEntity(
                                entity_id=ent_id,
                                run_id=run_id,
                                entity_type=ObservedEntityType.FILESYSTEM_PATH,
                                name=fpath,
                                normalized_value=fpath,
                                first_observed_at=ev.timestamp,
                                last_observed_at=ev.timestamp,
                                occurrence_count=1,
                                evidence_ids=[evidence_id],
                                attributes=ev.attributes,
                            )

            # 3. Process Spawn
            elif ev.event_type == RuntimeEventType.PROCESS_SPAWN:
                executable = ev.attributes.get("executable")
                if executable:
                    is_target_proc = False
                    if not target_process_identified:
                        is_target_proc = True
                        target_process_identified = True

                    key = f"process:{executable}"
                    if key in observed_map:
                        ent = observed_map[key]
                        ent.last_observed_at = ev.timestamp
                        ent.occurrence_count += 1
                        ent.evidence_ids.append(evidence_id)
                    else:
                        ent_id = generate_entity_id(ObservedEntityType.PROCESS.value, executable)
                        proc_attrs = dict(ev.attributes)
                        proc_attrs["is_target_process"] = is_target_proc
                        proc_attrs["process_role"] = "TARGET_PROCESS" if is_target_proc else "CHILD_PROCESS"
                        observed_map[key] = ObservedEntity(
                            entity_id=ent_id,
                            run_id=run_id,
                            entity_type=ObservedEntityType.PROCESS,
                            name=executable,
                            normalized_value=executable,
                            first_observed_at=ev.timestamp,
                            last_observed_at=ev.timestamp,
                            occurrence_count=1,
                            evidence_ids=[evidence_id],
                            attributes=proc_attrs,
                        )

        observed_model = ObservedModel(run_id=run_id, entities=list(observed_map.values()))
        return observed_model, all_evidence
