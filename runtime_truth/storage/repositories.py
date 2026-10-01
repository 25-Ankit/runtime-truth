"""Repository implementations for persisting and querying core models."""

import json
from datetime import datetime
from typing import List, Optional

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
from runtime_truth.core.models import (
    DeclaredEntity,
    Evidence,
    Finding,
    ObservedEntity,
    Run,
    RuntimeEvent,
    SourceLocation,
)
from runtime_truth.storage.database import Database


class RunRepository:
    def __init__(self, db: Database):
        self.db = db

    def save(self, run: Run) -> None:
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, project_path, started_at, finished_at, status,
                    tool_version, host_metadata, runtime_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    project_path=excluded.project_path,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    status=excluded.status,
                    tool_version=excluded.tool_version,
                    host_metadata=excluded.host_metadata,
                    runtime_mode=excluded.runtime_mode
                """,
                (
                    run.run_id,
                    run.project_path,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.status.value,
                    run.tool_version,
                    json.dumps(run.host_metadata),
                    run.runtime_mode.value,
                ),
            )

    def get(self, run_id: str) -> Optional[Run]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if not row:
                return None
            return Run(
                run_id=row["run_id"],
                project_path=row["project_path"],
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
                status=RunStatus(row["status"]),
                tool_version=row["tool_version"],
                host_metadata=json.loads(row["host_metadata"]),
                runtime_mode=RuntimeMode(row["runtime_mode"]),
            )

    def list_all(self, limit: int = 100) -> List[Run]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
            runs = []
            for row in cur.fetchall():
                runs.append(
                    Run(
                        run_id=row["run_id"],
                        project_path=row["project_path"],
                        started_at=datetime.fromisoformat(row["started_at"]),
                        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
                        status=RunStatus(row["status"]),
                        tool_version=row["tool_version"],
                        host_metadata=json.loads(row["host_metadata"]),
                        runtime_mode=RuntimeMode(row["runtime_mode"]),
                    )
                )
            return runs


class DeclaredEntityRepository:
    def __init__(self, db: Database):
        self.db = db

    def save_many(self, entities: List[DeclaredEntity]) -> None:
        if not entities:
            return
        with self.db.session() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO declared_entities (
                    entity_id, run_id, entity_type, name, normalized_value,
                    raw_value, source, source_location, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e.entity_id,
                        e.run_id,
                        e.entity_type.value,
                        e.name,
                        e.normalized_value,
                        e.raw_value,
                        e.source,
                        e.source_location.model_dump_json() if e.source_location else None,
                        json.dumps(e.metadata),
                    )
                    for e in entities
                ],
            )

    def get_by_run(self, run_id: str) -> List[DeclaredEntity]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM declared_entities WHERE run_id = ?", (run_id,))
            entities = []
            for row in cur.fetchall():
                source_loc = (
                    SourceLocation.model_validate_json(row["source_location"])
                    if row["source_location"]
                    else None
                )
                entities.append(
                    DeclaredEntity(
                        entity_id=row["entity_id"],
                        run_id=row["run_id"],
                        entity_type=DeclaredEntityType(row["entity_type"]),
                        name=row["name"],
                        normalized_value=row["normalized_value"],
                        raw_value=row["raw_value"],
                        source=row["source"],
                        source_location=source_loc,
                        metadata=json.loads(row["metadata"]),
                    )
                )
            return entities


class RuntimeEventRepository:
    def __init__(self, db: Database):
        self.db = db

    def save_many(self, events: List[RuntimeEvent]) -> None:
        if not events:
            return
        with self.db.session() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO runtime_events (
                    event_id, run_id, timestamp, pid, process,
                    event_type, attributes, source, raw_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        ev.event_id,
                        ev.run_id,
                        ev.timestamp.isoformat(),
                        ev.pid,
                        ev.process,
                        ev.event_type.value,
                        json.dumps(ev.attributes),
                        ev.source,
                        ev.raw_reference,
                    )
                    for ev in events
                ],
            )

    def get_by_run(self, run_id: str) -> List[RuntimeEvent]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM runtime_events WHERE run_id = ? ORDER BY timestamp ASC", (run_id,))
            events = []
            for row in cur.fetchall():
                events.append(
                    RuntimeEvent(
                        event_id=row["event_id"],
                        run_id=row["run_id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        pid=row["pid"],
                        process=row["process"],
                        event_type=RuntimeEventType(row["event_type"]),
                        attributes=json.loads(row["attributes"]),
                        source=row["source"],
                        raw_reference=row["raw_reference"],
                    )
                )
            return events


class ObservedEntityRepository:
    def __init__(self, db: Database):
        self.db = db

    def save_many(self, entities: List[ObservedEntity]) -> None:
        if not entities:
            return
        with self.db.session() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO observed_entities (
                    entity_id, run_id, entity_type, name, normalized_value,
                    first_observed_at, last_observed_at, occurrence_count,
                    evidence_ids, attributes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e.entity_id,
                        e.run_id,
                        e.entity_type.value,
                        e.name,
                        e.normalized_value,
                        e.first_observed_at.isoformat(),
                        e.last_observed_at.isoformat(),
                        e.occurrence_count,
                        json.dumps(e.evidence_ids),
                        json.dumps(e.attributes),
                    )
                    for e in entities
                ],
            )

    def get_by_run(self, run_id: str) -> List[ObservedEntity]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM observed_entities WHERE run_id = ?", (run_id,))
            entities = []
            for row in cur.fetchall():
                entities.append(
                    ObservedEntity(
                        entity_id=row["entity_id"],
                        run_id=row["run_id"],
                        entity_type=ObservedEntityType(row["entity_type"]),
                        name=row["name"],
                        normalized_value=row["normalized_value"],
                        first_observed_at=datetime.fromisoformat(row["first_observed_at"]),
                        last_observed_at=datetime.fromisoformat(row["last_observed_at"]),
                        occurrence_count=row["occurrence_count"],
                        evidence_ids=json.loads(row["evidence_ids"]),
                        attributes=json.loads(row["attributes"]),
                    )
                )
            return entities


class EvidenceRepository:
    def __init__(self, db: Database):
        self.db = db

    def save_many(self, evidence_list: List[Evidence]) -> None:
        if not evidence_list:
            return
        with self.db.session() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO evidence (
                    evidence_id, run_id, event_id, collector,
                    timestamp, description, raw_evidence, structured_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        evi.evidence_id,
                        evi.run_id,
                        evi.event_id,
                        evi.collector,
                        evi.timestamp.isoformat(),
                        evi.description,
                        evi.raw_evidence,
                        json.dumps(evi.structured_data),
                    )
                    for evi in evidence_list
                ],
            )

    def get_by_run(self, run_id: str) -> List[Evidence]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM evidence WHERE run_id = ?", (run_id,))
            evidence_list = []
            for row in cur.fetchall():
                evidence_list.append(
                    Evidence(
                        evidence_id=row["evidence_id"],
                        run_id=row["run_id"],
                        event_id=row["event_id"],
                        collector=row["collector"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        description=row["description"],
                        raw_evidence=row["raw_evidence"],
                        structured_data=json.loads(row["structured_data"]),
                    )
                )
            return evidence_list


class FindingRepository:
    def __init__(self, db: Database):
        self.db = db

    def save_many(self, findings: List[Finding]) -> None:
        if not findings:
            return
        with self.db.session() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO findings (
                    finding_id, run_id, category, finding_type, severity,
                    subject, declared_state, observed_state, explanation,
                    evidence_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f.finding_id,
                        f.run_id,
                        f.category.value,
                        f.finding_type.value,
                        f.severity.value,
                        f.subject,
                        json.dumps(f.declared_state) if f.declared_state else None,
                        json.dumps(f.observed_state) if f.observed_state else None,
                        f.explanation,
                        json.dumps(f.evidence_ids),
                        f.created_at.isoformat(),
                    )
                    for f in findings
                ],
            )

    def get_by_run(self, run_id: str) -> List[Finding]:
        with self.db.session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM findings WHERE run_id = ?", (run_id,))
            findings = []
            for row in cur.fetchall():
                findings.append(
                    Finding(
                        finding_id=row["finding_id"],
                        run_id=row["run_id"],
                        category=FindingCategory(row["category"]),
                        finding_type=FindingType(row["finding_type"]),
                        severity=FindingSeverity(row["severity"]),
                        subject=row["subject"],
                        declared_state=json.loads(row["declared_state"]) if row["declared_state"] else None,
                        observed_state=json.loads(row["observed_state"]) if row["observed_state"] else None,
                        explanation=row["explanation"],
                        evidence_ids=json.loads(row["evidence_ids"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
                )
            return findings
