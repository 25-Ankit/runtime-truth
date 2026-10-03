"""Builds ObservedModel and supporting Evidence records from canonical RuntimeEvents."""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from runtime_truth.core.enums import ObservedEntityType, RuntimeEventType
from runtime_truth.core.identifiers import generate_entity_id, generate_evidence_id
from runtime_truth.core.models import Evidence, ObservedEntity, ObservedModel, RuntimeEvent
from runtime_truth.observation.base import ObservedModelBuilder


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

    def build(self, events: List[RuntimeEvent], run_id: str) -> Tuple[ObservedModel, List[Evidence]]:
        observed_map: Dict[str, ObservedEntity] = {}
        all_evidence: List[Evidence] = []
        target_process_identified = False

        for ev in events:
            # Generate Evidence record for the event
            description = ""
            if ev.event_type == RuntimeEventType.NETWORK_CONNECT:
                dest = ev.attributes.get("destination", "unknown")
                port = ev.attributes.get("port", "")
                description = f"Observed network connection to {dest}:{port}"
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

            # Map to ObservedEntity
            # 1. Network Connect
            if ev.event_type == RuntimeEventType.NETWORK_CONNECT:
                dest = ev.attributes.get("destination")
                if dest and dest not in ("127.0.0.1", "::1", "0.0.0.0"):
                    norm_dest = dest.lower()
                    key = f"network:{norm_dest}"
                    if key in observed_map:
                        ent = observed_map[key]
                        ent.last_observed_at = ev.timestamp
                        ent.occurrence_count += 1
                        ent.evidence_ids.append(evidence_id)
                    else:
                        ent_id = generate_entity_id(ObservedEntityType.NETWORK_DESTINATION.value, norm_dest)
                        observed_map[key] = ObservedEntity(
                            entity_id=ent_id,
                            run_id=run_id,
                            entity_type=ObservedEntityType.NETWORK_DESTINATION,
                            name=dest,
                            normalized_value=norm_dest,
                            first_observed_at=ev.timestamp,
                            last_observed_at=ev.timestamp,
                            occurrence_count=1,
                            evidence_ids=[evidence_id],
                            attributes=ev.attributes,
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
