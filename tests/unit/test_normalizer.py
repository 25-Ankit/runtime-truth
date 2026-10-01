"""Unit tests for strace normalizer and observed model builder."""

from datetime import datetime, timezone
import pytest

from runtime_truth.core.enums import ObservedEntityType, RuntimeEventType
from runtime_truth.observation import CanonicalObservedModelBuilder, StraceEventNormalizer
from runtime_truth.runtime.base import RawEvent


def test_strace_normalizer_network_connect():
    normalizer = StraceEventNormalizer()
    raw = RawEvent(
        sequence=1,
        collector="strace",
        raw_payload='1234 10:15:30.123 connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.216.34")}, 16) = 0',
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )
    event = normalizer.normalize(raw, run_id="r1")
    assert event is not None
    assert event.event_type == RuntimeEventType.NETWORK_CONNECT
    assert event.pid == 1234
    assert event.attributes["destination"] == "93.184.216.34"
    assert event.attributes["port"] == 443
    assert event.attributes["protocol"] == "ipv4"


def test_strace_normalizer_file_syscalls():
    normalizer = StraceEventNormalizer()

    # File Read
    raw_read = RawEvent(
        sequence=1,
        collector="strace",
        raw_payload='openat(AT_FDCWD, "/app/config.json", O_RDONLY|O_CLOEXEC) = 3',
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )
    ev_read = normalizer.normalize(raw_read, run_id="r1")
    assert ev_read is not None
    assert ev_read.event_type == RuntimeEventType.FILE_READ
    assert ev_read.attributes["path"] == "/app/config.json"

    # File Create / Write
    raw_write = RawEvent(
        sequence=2,
        collector="strace",
        raw_payload='openat(AT_FDCWD, "/tmp/out.log", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 4',
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )
    ev_write = normalizer.normalize(raw_write, run_id="r1")
    assert ev_write is not None
    assert ev_write.event_type == RuntimeEventType.FILE_CREATE

    # File Delete
    raw_del = RawEvent(
        sequence=3,
        collector="strace",
        raw_payload='unlink("/tmp/tempfile.tmp") = 0',
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )
    ev_del = normalizer.normalize(raw_del, run_id="r1")
    assert ev_del is not None
    assert ev_del.event_type == RuntimeEventType.FILE_DELETE
    assert ev_del.attributes["path"] == "/tmp/tempfile.tmp"


def test_strace_normalizer_process():
    normalizer = StraceEventNormalizer()
    raw = RawEvent(
        sequence=1,
        collector="strace",
        raw_payload='execve("/usr/bin/python3", ["python3", "app.py"], [/* 30 vars */]) = 0',
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )
    ev = normalizer.normalize(raw, run_id="r1")
    assert ev is not None
    assert ev.event_type == RuntimeEventType.PROCESS_SPAWN
    assert ev.attributes["executable"] == "/usr/bin/python3"
    assert ev.attributes["args"] == ["python3", "app.py"]


def test_observed_model_builder_synthesis():
    builder = CanonicalObservedModelBuilder()
    now = datetime.now(timezone.utc)

    from runtime_truth.core.models import RuntimeEvent
    events = [
        # Network connect
        RuntimeEvent(
            event_id="e1",
            run_id="r1",
            timestamp=now,
            event_type=RuntimeEventType.NETWORK_CONNECT,
            attributes={"destination": "93.184.216.34", "port": 443},
            source="strace",
            raw_reference="connect(...)",
        ),
        # Python site-packages access -> dependency
        RuntimeEvent(
            event_id="e2",
            run_id="r1",
            timestamp=now,
            event_type=RuntimeEventType.FILE_READ,
            attributes={"path": "/usr/local/lib/python3.12/site-packages/requests/__init__.py"},
            source="strace",
            raw_reference="openat(...)",
        ),
        # Application file read -> filesystem_path
        RuntimeEvent(
            event_id="e3",
            run_id="r1",
            timestamp=now,
            event_type=RuntimeEventType.FILE_READ,
            attributes={"path": "/app/data/catalog.json"},
            source="strace",
            raw_reference="openat(...)",
        ),
        # Process spawn -> process
        RuntimeEvent(
            event_id="e4",
            run_id="r1",
            timestamp=now,
            event_type=RuntimeEventType.PROCESS_SPAWN,
            attributes={"executable": "/usr/bin/curl"},
            source="strace",
            raw_reference="execve(...)",
        ),
    ]

    model, evidence = builder.build(events, run_id="r1")
    assert len(evidence) == 4

    deps = model.get_by_type(ObservedEntityType.DEPENDENCY)
    assert len(deps) == 1
    assert deps[0].normalized_value == "requests"
    assert len(deps[0].evidence_ids) == 1

    nets = model.get_by_type(ObservedEntityType.NETWORK_DESTINATION)
    assert len(nets) == 1
    assert nets[0].normalized_value == "93.184.216.34"

    files = model.get_by_type(ObservedEntityType.FILESYSTEM_PATH)
    assert len(files) == 1
    assert files[0].normalized_value == "/app/data/catalog.json"

    procs = model.get_by_type(ObservedEntityType.PROCESS)
    assert len(procs) == 1
    assert procs[0].normalized_value == "/usr/bin/curl"
