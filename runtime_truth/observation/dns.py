"""DNS observation helpers: log loading, canonical normalization, identity tables.

DNS-specific wire/format knowledge lives here (and in runtime_truth.runtime.dns).
Reconciliation consumes only the normalized outputs (correlated_hostnames on
network entities), never raw DNS details.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from runtime_truth.core.enums import RuntimeEventType
from runtime_truth.core.errors import ObservationError
from runtime_truth.core.identifiers import generate_event_id
from runtime_truth.core.models import RuntimeEvent
from runtime_truth.observation.base import EventNormalizer
from runtime_truth.runtime.base import RawEvent

DNS_COLLECTOR_PREFIX = "dns_"
LIVE_DNS_COLLECTOR = "dns_stub"
OFFLINE_DNS_COLLECTOR = "dns_stub_offline"

SUCCESS_RCODES = {"NOERROR"}
DEFAULT_CORRELATION_WINDOW_SECONDS: float = 60.0


def as_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone for reliable comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_dns_collector(collector: str) -> bool:
    return collector.startswith(DNS_COLLECTOR_PREFIX)


class DnsLogLoader:
    """Loads stub-server JSONL DNS logs into RawEvents for deterministic replay."""

    def __init__(self, log_path: Path, collector: str = OFFLINE_DNS_COLLECTOR):
        self.log_path = Path(log_path)
        self.collector = collector
        self.last_dns_trace: Optional[List[Dict]] = None

    def is_available(self) -> bool:
        return self.log_path.exists() and self.log_path.is_file()

    def load(self, run_id: str = "") -> List[RawEvent]:
        if not self.is_available():
            raise ObservationError(f"DNS log file not found: {self.log_path}")
        try:
            content = self.log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise ObservationError(f"Failed to read DNS log file: {exc}") from exc
        records: List[Dict] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
        self.last_dns_trace = records
        now = datetime.now(timezone.utc)
        return [
            RawEvent(
                sequence=idx,
                collector=self.collector,
                raw_payload=json.dumps(rec),
                timestamp=now,
                metadata={"file": str(self.log_path), "line": idx, "run_id": run_id},
            )
            for idx, rec in enumerate(records, start=1)
        ]


class DnsEventNormalizer(EventNormalizer):
    """Normalizes stub-server JSON DNS records into canonical dns_resolution events."""

    def normalize(self, raw_event: RawEvent, run_id: str) -> Optional[RuntimeEvent]:
        try:
            record = json.loads(raw_event.raw_payload)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(record, dict):
            return None
        query_name = str(record.get("query_name", "")).strip().lower().rstrip(".")
        if not query_name:
            return None
        query_type = str(record.get("query_type", "A")).upper()
        answers = [str(a) for a in (record.get("answers") or [])]
        cname_chain = [str(c) for c in (record.get("cname_chain") or [])]
        rcode = str(record.get("rcode", "UNKNOWN"))
        try:
            ttl = int(record.get("ttl", 60))
        except (TypeError, ValueError):
            ttl = 60
        timestamp = raw_event.timestamp
        if raw_event.collector != OFFLINE_DNS_COLLECTOR:
            ts_raw = record.get("ts")
            if isinstance(ts_raw, str):
                try:
                    timestamp = datetime.fromisoformat(ts_raw)
                except ValueError:
                    pass
        event_id = generate_event_id(run_id, raw_event.raw_payload, raw_event.sequence)
        return RuntimeEvent(
            event_id=event_id,
            run_id=run_id,
            timestamp=timestamp,
            pid=None,  # stub observes at network boundary; no PID attribution available
            process=None,
            event_type=RuntimeEventType.DNS_RESOLUTION,
            attributes={
                "query_name": query_name,
                "query_type": query_type,
                "answers": answers,
                "cname_chain": cname_chain,
                "rcode": rcode,
                "ttl": ttl,
            },
            source=raw_event.collector,
            raw_reference=raw_event.raw_payload.strip(),
        )


def extract_dns_identity(event: RuntimeEvent) -> Optional[Tuple[str, List[str]]]:
    """Return (query_name, answers) for successful resolutions, else None.

    Successful = rcode NOERROR with at least one A/AAAA answer. Failed
    resolutions (NXDOMAIN/SERVFAIL/empty) yield evidence only, never identity.
    """
    if event.event_type != RuntimeEventType.DNS_RESOLUTION:
        return None
    if event.attributes.get("rcode") not in SUCCESS_RCODES:
        return None
    answers = [a for a in (event.attributes.get("answers") or []) if a]
    if not answers:
        return None
    query_name = str(event.attributes.get("query_name", "")).strip().lower()
    if not query_name:
        return None
    return query_name, answers


def build_dns_identity_table(
    dns_events: List[RuntimeEvent],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build same-run identity tables: ip -> hostnames, hostname -> ips.

    Scope rule (v1, documented): every successful resolution observed during
    the run may justify correlation with a connection observed during the same
    run. No TTL expiry or cross-run caching is applied; TTL values are
    preserved in event attributes for future enforcement.
    """
    ip_to_names: Dict[str, Set[str]] = {}
    name_to_ips: Dict[str, Set[str]] = {}
    for ev in dns_events:
        identity = extract_dns_identity(ev)
        if identity is None:
            continue
        name, answers = identity
        name_to_ips.setdefault(name, set()).update(answers)
        for ip in answers:
            ip_to_names.setdefault(ip, set()).add(name)
    return ip_to_names, name_to_ips
