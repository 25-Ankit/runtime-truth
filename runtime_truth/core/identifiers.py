"""Deterministic identifier generation for entities, events, evidence, and findings."""

import hashlib
import time
import uuid


def generate_run_id(prefix: str = "run") -> str:
    """Generate a unique run ID incorporating timestamp and short entropy."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    entropy = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{entropy}"


def generate_entity_id(entity_type: str, normalized_value: str, qualifier: str = "") -> str:
    """Generate a deterministic, stable entity ID."""
    payload = f"{entity_type.strip().lower()}:{normalized_value.strip().lower()}:{qualifier.strip()}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"ent_{digest}"


def generate_event_id(run_id: str, raw_reference: str, index: int = 0) -> str:
    """Generate a stable event ID within a run."""
    payload = f"{run_id}:{raw_reference}:{index}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"evt_{digest}"


def generate_evidence_id(run_id: str, collector: str, subject: str) -> str:
    """Generate a stable evidence ID."""
    payload = f"{run_id}:{collector}:{subject}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"evi_{digest}"


def generate_finding_id(run_id: str, finding_type: str, subject: str) -> str:
    """Generate a stable finding ID."""
    payload = f"{run_id}:{finding_type}:{subject.strip().lower()}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"fnd_{digest}"
