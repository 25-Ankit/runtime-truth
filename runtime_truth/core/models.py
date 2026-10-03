"""Core Pydantic domain models for Runtime Truth."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from runtime_truth.core.enums import (
    DeclaredEntityType,
    FindingCategory,
    FindingSeverity,
    FindingType,
    ObservedEntityType,
    RunStatus,
    RuntimeEventType,
    RuntimeMode,
)


class SourceLocation(BaseModel):
    """Pinpoints the static source of a declaration."""
    file_path: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None


class Run(BaseModel):
    """Tracks a single analysis or execution run."""
    run_id: str
    project_path: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    status: RunStatus = RunStatus.PENDING
    tool_version: str = "0.1.0"
    host_metadata: Dict[str, Any] = Field(default_factory=dict)
    runtime_mode: RuntimeMode = RuntimeMode.STATIC_ONLY


class DeclaredEntity(BaseModel):
    """An entity declared by the project configuration, source code, or manifests."""
    entity_id: str
    run_id: str
    entity_type: DeclaredEntityType
    name: str
    normalized_value: str
    raw_value: Optional[str] = None
    source: str
    source_location: Optional[SourceLocation] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimeEvent(BaseModel):
    """Canonical normalized runtime event emitted by an observation backend."""
    event_id: str
    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pid: Optional[int] = None
    process: Optional[str] = None
    event_type: RuntimeEventType
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source: str
    raw_reference: Optional[str] = None


class ObservedEntity(BaseModel):
    """Aggregated runtime behavior synthesized from canonical events."""
    entity_id: str
    run_id: str
    entity_type: ObservedEntityType
    name: str
    normalized_value: str
    first_observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    occurrence_count: int = 1
    evidence_ids: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Evidence record explaining why the system inferred a state or behavior."""
    evidence_id: str
    run_id: str
    event_id: Optional[str] = None
    collector: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str
    raw_evidence: Optional[str] = None
    structured_data: Dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    """A discrepancy or verified condition between declared and observed models."""
    finding_id: str
    run_id: str
    category: FindingCategory
    finding_type: FindingType
    severity: FindingSeverity = FindingSeverity.MEDIUM
    subject: str
    declared_state: Optional[Dict[str, Any]] = None
    observed_state: Optional[Dict[str, Any]] = None
    explanation: str
    evidence_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeclaredModel(BaseModel):
    """Aggregated declared entities for a project."""
    run_id: str
    entities: List[DeclaredEntity] = Field(default_factory=list)

    def get_by_type(self, entity_type: DeclaredEntityType) -> List[DeclaredEntity]:
        return [e for e in self.entities if e.entity_type == entity_type]

    def get_by_normalized_value(self, entity_type: DeclaredEntityType, val: str) -> Optional[DeclaredEntity]:
        val_lower = val.strip().lower()
        for e in self.entities:
            if e.entity_type == entity_type and e.normalized_value.lower() == val_lower:
                return e
        return None


class ObservedModel(BaseModel):
    """Aggregated observed entities for a runtime execution."""
    run_id: str
    entities: List[ObservedEntity] = Field(default_factory=list)

    def get_by_type(self, entity_type: ObservedEntityType) -> List[ObservedEntity]:
        if entity_type in (ObservedEntityType.DEPENDENCY, ObservedEntityType.PACKAGE_ARTIFACT):
            return [
                e for e in self.entities
                if e.entity_type in (ObservedEntityType.DEPENDENCY, ObservedEntityType.PACKAGE_ARTIFACT)
            ]
        return [e for e in self.entities if e.entity_type == entity_type]

    def get_by_normalized_value(self, entity_type: ObservedEntityType, val: str) -> Optional[ObservedEntity]:
        val_lower = val.strip().lower()
        target_types = (
            (ObservedEntityType.DEPENDENCY, ObservedEntityType.PACKAGE_ARTIFACT)
            if entity_type in (ObservedEntityType.DEPENDENCY, ObservedEntityType.PACKAGE_ARTIFACT)
            else (entity_type,)
        )
        for e in self.entities:
            if e.entity_type in target_types and e.normalized_value.lower() == val_lower:
                return e
        return None
