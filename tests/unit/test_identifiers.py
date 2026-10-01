"""Unit tests for deterministic identifier generation."""

from runtime_truth.core.identifiers import (
    generate_entity_id,
    generate_event_id,
    generate_evidence_id,
    generate_finding_id,
    generate_run_id,
)


def test_entity_id_determinism():
    id1 = generate_entity_id("dependency", "requests")
    id2 = generate_entity_id("dependency", "REQUESTS")
    id3 = generate_entity_id("dependency", "flask")

    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("ent_")


def test_entity_id_with_qualifier():
    id1 = generate_entity_id("dependency", "requests", qualifier="ast:app.py:10")
    id2 = generate_entity_id("dependency", "requests", qualifier="ast:app.py:10")
    id3 = generate_entity_id("dependency", "requests", qualifier="ast:app.py:20")

    assert id1 == id2
    assert id1 != id3


def test_finding_id_determinism():
    f1 = generate_finding_id("run_1", "NETWORK_OBSERVED_NOT_DECLARED", "93.184.216.34")
    f2 = generate_finding_id("run_1", "NETWORK_OBSERVED_NOT_DECLARED", "93.184.216.34")
    f3 = generate_finding_id("run_2", "NETWORK_OBSERVED_NOT_DECLARED", "93.184.216.34")

    assert f1 == f2
    assert f1 != f3
    assert f1.startswith("fnd_")


def test_event_and_evidence_ids():
    ev1 = generate_event_id("run_1", "connect(...)", 1)
    ev2 = generate_event_id("run_1", "connect(...)", 1)
    assert ev1 == ev2
    assert ev1.startswith("evt_")

    evi1 = generate_evidence_id("run_1", "strace", "dest_1")
    evi2 = generate_evidence_id("run_1", "strace", "dest_1")
    assert evi1 == evi2
    assert evi1.startswith("evi_")


def test_run_id_generation():
    r1 = generate_run_id()
    r2 = generate_run_id()
    assert r1.startswith("run_")
    assert r1 != r2
