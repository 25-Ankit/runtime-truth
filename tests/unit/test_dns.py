"""Unit tests for DNS resolution events, identity tables, and correlation."""

import json
from datetime import datetime, timezone

import pytest

from runtime_truth.core.enums import FindingType, RuntimeEventType
from runtime_truth.core.models import RuntimeEvent
from runtime_truth.observation.dns import (
    DnsEventNormalizer,
    DnsLogLoader,
    build_dns_identity_table,
    extract_dns_identity,
    is_dns_collector,
)
from runtime_truth.runtime.base import RawEvent


def _raw(seq, payload, collector="dns_stub"):
    return RawEvent(
        sequence=seq,
        collector=collector,
        raw_payload=payload,
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )


def _dns_event(eid, qname, answers, rcode="NOERROR", qtype="A", chain=None, ts=None):
    return RuntimeEvent(
        event_id=eid,
        run_id="r",
        timestamp=ts or datetime.now(timezone.utc),
        event_type=RuntimeEventType.DNS_RESOLUTION,
        attributes={
            "query_name": qname,
            "query_type": qtype,
            "answers": answers,
            "cname_chain": chain or [],
            "rcode": rcode,
            "ttl": 60,
        },
        source="dns_stub",
        raw_reference="{}",
    )


def test_is_dns_collector_routing():
    assert is_dns_collector("dns_stub")
    assert is_dns_collector("dns_stub_offline")
    assert not is_dns_collector("strace_docker")
    assert not is_dns_collector("strace_offline")


def test_dns_normalizer_a_record():
    norm = DnsEventNormalizer()
    rec = {
        "ts": "2026-10-03T07:00:00.100000+00:00",
        "client": "172.18.0.3",
        "query_name": "api.example.com",
        "query_type": "A",
        "answers": ["93.184.216.34"],
        "cname_chain": [],
        "rcode": "NOERROR",
        "ttl": 60,
    }
    ev = norm.normalize(_raw(1, json.dumps(rec)), "r1")
    assert ev is not None
    assert ev.event_type == RuntimeEventType.DNS_RESOLUTION
    assert ev.attributes["query_name"] == "api.example.com"
    assert ev.attributes["query_type"] == "A"
    assert ev.attributes["answers"] == ["93.184.216.34"]
    assert ev.attributes["rcode"] == "NOERROR"
    assert ev.pid is None  # network-boundary observer: no PID attribution
    assert ev.raw_reference == json.dumps(rec)


def test_dns_normalizer_aaaa_record():
    norm = DnsEventNormalizer()
    rec = {
        "query_name": "v6.example.com",
        "query_type": "AAAA",
        "answers": ["2001:db8::1"],
        "cname_chain": [],
        "rcode": "NOERROR",
        "ttl": 60,
    }
    ev = norm.normalize(_raw(1, json.dumps(rec)), "r1")
    assert ev is not None
    assert ev.attributes["query_type"] == "AAAA"
    assert ev.attributes["answers"] == ["2001:db8::1"]


def test_dns_normalizer_cname_chain_preserved():
    norm = DnsEventNormalizer()
    rec = {
        "query_name": "app.example.com",
        "query_type": "A",
        "answers": ["93.184.216.34"],
        "cname_chain": ["backend.example.net"],
        "rcode": "NOERROR",
        "ttl": 60,
    }
    ev = norm.normalize(_raw(1, json.dumps(rec)), "r1")
    assert ev is not None
    assert ev.attributes["cname_chain"] == ["backend.example.net"]
    assert ev.attributes["answers"] == ["93.184.216.34"]


def test_dns_normalizer_failed_resolution():
    norm = DnsEventNormalizer()
    rec = {
        "query_name": "nope.example.com",
        "query_type": "A",
        "answers": [],
        "cname_chain": [],
        "rcode": "NXDOMAIN",
        "ttl": 60,
    }
    ev = norm.normalize(_raw(1, json.dumps(rec)), "r1")
    assert ev is not None
    assert ev.attributes["rcode"] == "NXDOMAIN"
    assert ev.attributes["answers"] == []
    # Failed resolutions normalize (evidence preserved) but yield no identity
    assert extract_dns_identity(ev) is None


def test_dns_normalizer_rejects_garbage():
    norm = DnsEventNormalizer()
    assert norm.normalize(_raw(1, "not json at all"), "r1") is None
    assert norm.normalize(_raw(1, json.dumps({"answers": ["1.2.3.4"]})), "r1") is None
    assert norm.normalize(_raw(1, json.dumps(["list"])), "r1") is None


def test_extract_dns_identity_success_and_failures():
    assert extract_dns_identity(_dns_event("a", "h.example.com", ["1.2.3.4"])) == (
        "h.example.com",
        ["1.2.3.4"],
    )
    assert extract_dns_identity(_dns_event("b", "h.example.com", [], "NXDOMAIN")) is None
    assert extract_dns_identity(_dns_event("c", "h.example.com", [], "NOERROR")) is None
    non_dns = RuntimeEvent(
        event_id="x",
        run_id="r",
        timestamp=datetime.now(timezone.utc),
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "1.2.3.4"},
        source="strace",
        raw_reference="x",
    )
    assert extract_dns_identity(non_dns) is None


def test_identity_table_multiple_hostnames_same_ip():
    # No arbitrary choice: all identities preserved per IP.
    table, reverse = build_dns_identity_table(
        [
            _dns_event("a", "api.example.com", ["93.184.216.34"]),
            _dns_event("b", "backend.example.net", ["93.184.216.34"]),
            _dns_event("c", "gone.example.com", [], "NXDOMAIN"),
        ]
    )
    assert table["93.184.216.34"] == {"api.example.com", "backend.example.net"}
    assert reverse["api.example.com"] == {"93.184.216.34"}
    assert "gone.example.com" not in reverse


def test_dns_log_loader_roundtrip(tmp_path):
    log = tmp_path / "dns.jsonl"
    rec = {
        "query_name": "api.example.com",
        "query_type": "A",
        "answers": ["93.184.216.34"],
        "cname_chain": [],
        "rcode": "NOERROR",
        "ttl": 60,
    }
    log.write_text(json.dumps(rec) + "\n")
    loader = DnsLogLoader(log)
    raw_events = loader.load(run_id="r1")
    assert len(raw_events) == 1
    assert raw_events[0].collector == "dns_stub_offline"
    ev = DnsEventNormalizer().normalize(raw_events[0], "r1")
    assert ev is not None
    assert ev.attributes["answers"] == ["93.184.216.34"]


def test_dns_log_loader_missing_file(tmp_path):
    from runtime_truth.core.errors import ObservationError

    with pytest.raises(ObservationError):
        DnsLogLoader(tmp_path / "absent.jsonl").load()


# --- Correlation semantics (CASE A/B/C/D) via ReconciliationEngine ---

from runtime_truth.core.enums import DeclaredEntityType, ObservedEntityType
from runtime_truth.core.models import DeclaredEntity, DeclaredModel, ObservedEntity, ObservedModel
from runtime_truth.reconciliation.engine import ReconciliationEngine


def _declared_net(eid, name, source="config.json"):
    return DeclaredEntity(
        entity_id=eid, run_id="r", entity_type=DeclaredEntityType.NETWORK_DESTINATION,
        name=name, normalized_value=name.lower(), source=source,
    )


def _observed_net(eid, ip, hostnames, count=1):
    now = datetime.now(timezone.utc)
    return ObservedEntity(
        entity_id=eid, run_id="r", entity_type=ObservedEntityType.NETWORK_DESTINATION,
        name=ip, normalized_value=ip.lower(),
        first_observed_at=now, last_observed_at=now,
        occurrence_count=count, evidence_ids=["evi_dns", "evi_conn"],
        attributes={"correlated_hostnames": hostnames, "port": 443},
    )


def test_case_a_declared_matched_via_dns():
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    observed = ObservedModel(
        run_id="r", entities=[_observed_net("o1", "93.184.216.34", ["api.example.com"])]
    )
    findings = engine.reconcile(declared, observed)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED not in types
    assert FindingType.NETWORK_DECLARED_NOT_OBSERVED not in types
    assert FindingType.NETWORK_OBSERVED_NOT_DECLARED not in types
    assert findings == []


def test_case_b_unrelated_identity_still_flagged():
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    observed = ObservedModel(
        run_id="r",
        entities=[
            _observed_net("o1", "93.184.216.34", ["api.example.com"]),
            _observed_net("o2", "203.0.113.20", ["telemetry.example.net"]),
        ],
    )
    findings = engine.reconcile(declared, observed)
    by_type = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED not in by_type
    flagged = [f for f in findings if f.finding_type == FindingType.NETWORK_OBSERVED_NOT_DECLARED]
    assert len(flagged) == 1
    assert flagged[0].subject == "telemetry.example.net"
    assert "203.0.113.20" in flagged[0].explanation


def test_case_c_no_dns_evidence_stays_uncorrelated():
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    observed = ObservedModel(
        run_id="r", entities=[_observed_net("o1", "93.184.216.34", [])]
    )
    findings = engine.reconcile(declared, observed)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED in types
    assert FindingType.NETWORK_OBSERVED_NOT_DECLARED not in types


def test_case_d_failed_resolution_yields_evidence_only():
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    now = datetime.now(timezone.utc)
    fail = RuntimeEvent(
        event_id="dns-fail", run_id="r", timestamp=now,
        event_type=RuntimeEventType.DNS_RESOLUTION,
        attributes={"query_name": "api.example.com", "query_type": "A",
                    "answers": [], "cname_chain": [], "rcode": "NXDOMAIN", "ttl": 60},
        source="dns_stub", raw_reference="{}",
    )
    model, evidence = CanonicalObservedModelBuilder().build([fail], "r")
    assert len(evidence) == 1  # DNS failure evidence preserved
    assert model.entities == []  # but never a network destination


def test_builder_links_dns_and_connect_evidence():
    from datetime import timedelta
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    t0 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    dns = _dns_event("d1", "api.example.com", ["93.184.216.34"], ts=t0)
    conn = RuntimeEvent(
        event_id="c1", run_id="r", timestamp=t0 + timedelta(milliseconds=10),
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "93.184.216.34", "port": 443},
        source="strace_docker", raw_reference="connect(...)",
    )
    model, evidence = CanonicalObservedModelBuilder().build([conn, dns], "r")
    nets = model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
    assert len(nets) == 1
    assert nets[0].attributes["correlated_hostnames"] == ["api.example.com"]
    # connect evidence + DNS evidence both linked
    assert len(nets[0].evidence_ids) == 2
    assert len(evidence) == 2


def test_two_hostnames_same_ip_ambiguous():
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[])
    observed = ObservedModel(
        run_id="r",
        entities=[
            _observed_net(
                "o1", "93.184.216.34", ["api.example.com", "telemetry.example.com"]
            )
        ],
    )
    findings = engine.reconcile(declared, observed)
    types = [f.finding_type for f in findings]
    assert FindingType.NETWORK_IDENTITY_AMBIGUOUS in types
    assert FindingType.NETWORK_OBSERVED_NOT_DECLARED not in types
    f = next(f for f in findings if f.finding_type == FindingType.NETWORK_IDENTITY_AMBIGUOUS)
    assert f.subject == "93.184.216.34"
    assert "api.example.com" in f.explanation
    assert "telemetry.example.com" in f.explanation
    assert "cannot be disambiguated" in f.explanation


def test_multiple_hostnames_with_only_one_declared():
    # When api.example.com is declared but telemetry.example.com also resolved to the same IP,
    # we cannot assume the connection was to api.example.com.
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    observed = ObservedModel(
        run_id="r",
        entities=[
            _observed_net(
                "o1", "93.184.216.34", ["api.example.com", "telemetry.example.com"]
            )
        ],
    )
    findings = engine.reconcile(declared, observed)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_AMBIGUOUS in types
    assert FindingType.NETWORK_DECLARED_NOT_OBSERVED in types
    assert FindingType.NETWORK_OBSERVED_NOT_DECLARED not in types


def test_multiple_hostnames_both_declared():
    # Both api.example.com and telemetry.example.com are declared, but share destination IP.
    engine = ReconciliationEngine()
    declared = DeclaredModel(
        run_id="r",
        entities=[
            _declared_net("d1", "api.example.com"),
            _declared_net("d2", "telemetry.example.com"),
        ],
    )
    observed = ObservedModel(
        run_id="r",
        entities=[
            _observed_net(
                "o1", "93.184.216.34", ["api.example.com", "telemetry.example.com"]
            )
        ],
    )
    findings = engine.reconcile(declared, observed)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_AMBIGUOUS in types
    declared_not_observed = [
        f.subject for f in findings if f.finding_type == FindingType.NETWORK_DECLARED_NOT_OBSERVED
    ]
    assert "api.example.com" in declared_not_observed
    assert "telemetry.example.com" in declared_not_observed


def test_multiple_a_answers_unambiguous():
    from datetime import timedelta
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    t0 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    # api.example.com resolves to 2 IPs: 93.184.216.34 and 93.184.216.35
    dns = _dns_event("d1", "api.example.com", ["93.184.216.34", "93.184.216.35"], ts=t0)
    conn = RuntimeEvent(
        event_id="c1", run_id="r", timestamp=t0 + timedelta(milliseconds=10),
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "93.184.216.34", "port": 443},
        source="strace_docker", raw_reference="connect(...)",
    )
    model, evidence = CanonicalObservedModelBuilder().build([conn, dns], "r")
    nets = model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
    assert len(nets) == 1
    assert nets[0].attributes["correlated_hostnames"] == ["api.example.com"]
    assert nets[0].attributes["correlation_status"] == "RESOLVED"

    # Reconciliation with api.example.com declared matches
    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    findings = engine.reconcile(declared, model)
    assert len(findings) == 0


def test_connection_after_correlation_window_unresolved():
    from datetime import timedelta
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    t0 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    dns = RuntimeEvent(
        event_id="d1", run_id="r", timestamp=t0,
        event_type=RuntimeEventType.DNS_RESOLUTION,
        attributes={"query_name": "api.example.com", "query_type": "A",
                    "answers": ["93.184.216.34"], "cname_chain": [], "rcode": "NOERROR", "ttl": 60},
        source="dns_stub", raw_reference="{}",
    )
    # Connection occurs 120 seconds later (outside default 60s correlation window)
    t_conn = t0 + timedelta(seconds=120)
    conn = RuntimeEvent(
        event_id="c1", run_id="r", timestamp=t_conn,
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "93.184.216.34", "port": 443},
        source="strace_docker", raw_reference="connect(...)",
    )
    builder = CanonicalObservedModelBuilder(correlation_window_seconds=60.0)
    model, evidence = builder.build([dns, conn], "r")
    nets = model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
    assert len(nets) == 1
    assert nets[0].attributes["correlated_hostnames"] == []
    assert nets[0].attributes["correlation_status"] == "UNRESOLVED"

    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    findings = engine.reconcile(declared, model)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED in types
    assert FindingType.NETWORK_DECLARED_NOT_OBSERVED in types


def test_connection_before_observed_dns_resolution_unresolved():
    from datetime import timedelta
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    t0 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    # Connection happens at t0
    conn = RuntimeEvent(
        event_id="c1", run_id="r", timestamp=t0,
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "93.184.216.34", "port": 443},
        source="strace_docker", raw_reference="connect(...)",
    )
    # DNS resolution happens 10 seconds LATER
    dns = RuntimeEvent(
        event_id="d1", run_id="r", timestamp=t0 + timedelta(seconds=10),
        event_type=RuntimeEventType.DNS_RESOLUTION,
        attributes={"query_name": "api.example.com", "query_type": "A",
                    "answers": ["93.184.216.34"], "cname_chain": [], "rcode": "NOERROR", "ttl": 60},
        source="dns_stub", raw_reference="{}",
    )
    builder = CanonicalObservedModelBuilder(correlation_window_seconds=60.0)
    model, evidence = builder.build([conn, dns], "r")
    nets = model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
    assert len(nets) == 1
    assert nets[0].attributes["correlated_hostnames"] == []
    assert nets[0].attributes["correlation_status"] == "UNRESOLVED"

    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    findings = engine.reconcile(declared, model)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED in types


def test_hardcoded_ip_unresolved():
    # Target connects directly to 93.184.216.34 without any prior DNS lookup
    now = datetime.now(timezone.utc)
    conn = RuntimeEvent(
        event_id="c1", run_id="r", timestamp=now,
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "93.184.216.34", "port": 443},
        source="strace_docker", raw_reference="connect(...)",
    )
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    model, evidence = CanonicalObservedModelBuilder().build([conn], "r")
    nets = model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
    assert len(nets) == 1
    assert nets[0].attributes["correlated_hostnames"] == []
    assert nets[0].attributes["correlation_status"] == "UNRESOLVED"

    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "api.example.com")])
    findings = engine.reconcile(declared, model)
    types = {f.finding_type for f in findings}
    assert FindingType.NETWORK_IDENTITY_UNCORRELATED in types


def test_ipv6_equivalent_behavior_matched_and_ambiguous():
    from datetime import timedelta
    from runtime_truth.observation.builder import CanonicalObservedModelBuilder

    t0 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Unambiguous IPv6 match
    dns6 = _dns_event("d6_1", "v6.example.com", ["2001:db8::1"], qtype="AAAA", ts=t0)
    conn6 = RuntimeEvent(
        event_id="c6_1", run_id="r", timestamp=t0 + timedelta(milliseconds=10),
        event_type=RuntimeEventType.NETWORK_CONNECT,
        attributes={"destination": "2001:db8::1", "port": 443},
        source="strace_docker", raw_reference="connect(...)",
    )
    model1, _ = CanonicalObservedModelBuilder().build([dns6, conn6], "r")
    net1 = model1.get_by_type(ObservedEntityType.NETWORK_DESTINATION)[0]
    assert net1.attributes["correlated_hostnames"] == ["v6.example.com"]

    engine = ReconciliationEngine()
    declared = DeclaredModel(run_id="r", entities=[_declared_net("d1", "v6.example.com")])
    findings1 = engine.reconcile(declared, model1)
    assert len(findings1) == 0  # MATCHED

    # 2. Ambiguous IPv6 (two hostnames resolve to same IPv6 address)
    dns6_alt = _dns_event("d6_2", "v6-alt.example.com", ["2001:db8::1"], qtype="AAAA", ts=t0)
    model2, _ = CanonicalObservedModelBuilder().build([dns6, dns6_alt, conn6], "r")
    net2 = model2.get_by_type(ObservedEntityType.NETWORK_DESTINATION)[0]
    assert sorted(net2.attributes["correlated_hostnames"]) == ["v6-alt.example.com", "v6.example.com"]
    assert net2.attributes["correlation_status"] == "AMBIGUOUS"

    findings2 = engine.reconcile(declared, model2)
    types2 = {f.finding_type for f in findings2}
    assert FindingType.NETWORK_IDENTITY_AMBIGUOUS in types2
    assert FindingType.NETWORK_OBSERVED_NOT_DECLARED not in types2
