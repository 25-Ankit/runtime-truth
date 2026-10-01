"""Evidence store answering why the system inferred state or behavior."""

from typing import Dict, List, Optional

from runtime_truth.core.models import Evidence


class EvidenceStore:
    """Manages evidence records for traceability and verification."""

    def __init__(self, initial_evidence: Optional[List[Evidence]] = None):
        self._store: Dict[str, Evidence] = {}
        if initial_evidence:
            self.add_many(initial_evidence)

    def add(self, evidence: Evidence) -> None:
        self._store[evidence.evidence_id] = evidence

    def add_many(self, evidence_list: List[Evidence]) -> None:
        for item in evidence_list:
            self._store[item.evidence_id] = item

    def get(self, evidence_id: str) -> Optional[Evidence]:
        return self._store.get(evidence_id)

    def get_by_ids(self, evidence_ids: List[str]) -> List[Evidence]:
        return [self._store[eid] for eid in evidence_ids if eid in self._store]

    def get_by_run(self, run_id: str) -> List[Evidence]:
        return [item for item in self._store.values() if item.run_id == run_id]

    def all(self) -> List[Evidence]:
        return list(self._store.values())
