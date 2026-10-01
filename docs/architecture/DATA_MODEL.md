# Runtime Truth: Data Model Specification

## Domain Entities

All core models are defined as immutable, typed Pydantic v2 schemas located in `runtime_truth.core.models`.

---

### 1. `Run`
Represents an execution instance of Runtime Truth over a target project.

| Field | Type | Description |
|---|---|---|
| `run_id` | `str` | Unique identifier (e.g. `run_YYYYMMDD_HHMMSS_<hex>`) |
| `project_path` | `str` | Absolute path of target project |
| `started_at` | `datetime` | UTC timestamp when analysis started |
| `finished_at` | `Optional[datetime]` | UTC timestamp when analysis completed |
| `status` | `RunStatus` | `pending`, `running`, `completed`, `failed` |
| `tool_version` | `str` | Version of Runtime Truth (e.g. `0.1.0`) |
| `host_metadata` | `Dict[str, Any]` | Platform OS, Python version, architecture |
| `runtime_mode` | `RuntimeMode` | `static_only`, `offline_events`, `host_strace`, `container_strace` |

---

### 2. `DeclaredEntity`
Represents an asset, configuration, or dependency declared statically in project manifests or source code.

| Field | Type | Description |
|---|---|---|
| `entity_id` | `str` | Deterministic hash ID `ent_<hex16>` |
| `run_id` | `str` | Reference to parent `Run` |
| `entity_type` | `DeclaredEntityType` | `dependency`, `network_destination`, `filesystem_path`, `environment_variable`, `process`, `port` |
| `name` | `str` | Raw identifier or package name |
| `normalized_value` | `str` | Canonical normalized value (e.g. lowercase package name) |
| `raw_value` | `Optional[str]` | Verbatim line or declaration text |
| `source` | `str` | Source manifest path (e.g. `requirements.txt`, `Dockerfile`) |
| `source_location` | `Optional[SourceLocation]` | Specific file path, line number, column number |
| `metadata` | `Dict[str, Any]` | Version constraints, extras, instruction type |

---

### 3. `RuntimeEvent` (Canonical Event Contract)
Shared event structure emitted by all observation normalizers.

```json
{
  "event_id": "evt_4a781290bc5e31fa",
  "run_id": "run_20261001_120000_1234abcd",
  "timestamp": "2026-10-01T12:00:00.030000+00:00",
  "pid": 1000,
  "process": "python",
  "event_type": "network_connect",
  "attributes": {
    "destination": "93.184.216.34",
    "port": 443,
    "protocol": "ipv4"
  },
  "source": "strace",
  "raw_reference": "connect(7, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr(\"93.184.216.34\")}, 16) = 0"
}
```

| Field | Type | Description |
|---|---|---|
| `event_id` | `str` | Deterministic hash ID `evt_<hex16>` |
| `run_id` | `str` | Reference to parent `Run` |
| `timestamp` | `datetime` | UTC timestamp of observation |
| `pid` | `Optional[int]` | Operating system process identifier |
| `process` | `Optional[str]` | Executable path |
| `event_type` | `RuntimeEventType` | `process_spawn`, `process_exit`, `network_connect`, `dns_resolution`, `file_read`, `file_write`, `file_create`, `file_delete`, `environment_access` |
| `attributes` | `Dict[str, Any]` | Extracted event attributes (destination, port, path, args) |
| `source` | `str` | Collector identifier (`strace_host`, `strace_docker`, `strace_offline`) |
| `raw_reference` | `Optional[str]` | Verbatim log entry |

---

### 4. `ObservedEntity`
Represents runtime behavior aggregated from one or more canonical events.

| Field | Type | Description |
|---|---|---|
| `entity_id` | `str` | Deterministic hash ID `ent_<hex16>` |
| `run_id` | `str` | Reference to parent `Run` |
| `entity_type` | `ObservedEntityType` | `dependency`, `network_destination`, `filesystem_path`, `environment_variable`, `process` |
| `name` | `str` | Observed resource name |
| `normalized_value` | `str` | Canonical normalized value |
| `first_observed_at` | `datetime` | Timestamp of first occurrence |
| `last_observed_at` | `datetime` | Timestamp of latest occurrence |
| `occurrence_count` | `int` | Number of events contributing to this entity |
| `evidence_ids` | `List[str]` | References to supporting `Evidence` records |
| `attributes` | `Dict[str, Any]` | Supporting telemetry metadata |

---

### 5. `Evidence`
Provides verifiable justification for why the system inferred a runtime entity or finding.

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `str` | Deterministic hash ID `evi_<hex16>` |
| `run_id` | `str` | Reference to parent `Run` |
| `event_id` | `Optional[str]` | Associated canonical `RuntimeEvent` ID |
| `collector` | `str` | Observer backend name |
| `timestamp` | `datetime` | UTC timestamp of recorded event |
| `description` | `str` | Human-readable description |
| `raw_evidence` | `Optional[str]` | Verbatim raw log reference |
| `structured_data` | `Dict[str, Any]` | Parsed event payload |

---

### 6. `Finding`
Records a discrepancy or observation between the Declared Model and Observed Model.

| Field | Type | Description |
|---|---|---|
| `finding_id` | `str` | Deterministic hash ID `fnd_<hex16>` |
| `run_id` | `str` | Reference to parent `Run` |
| `category` | `FindingCategory` | `dependency`, `network`, `filesystem`, `process`, `environment`, `behavior` |
| `finding_type` | `FindingType` | Discrepancy identifier (e.g. `RUNTIME_DEPENDENCY_NOT_DECLARED`) |
| `severity` | `FindingSeverity` | `info`, `low`, `medium`, `high` |
| `subject` | `str` | Target entity (e.g. package name, destination IP, file path) |
| `declared_state` | `Optional[Dict]` | Serialized declaration details if declared |
| `observed_state` | `Optional[Dict]` | Serialized runtime observation details if observed |
| `explanation` | `str` | Plain language discrepancy explanation |
| `evidence_ids` | `List[str]` | Supporting evidence IDs |
| `created_at` | `datetime` | UTC creation timestamp |

---

## Deterministic Identifier Generation

Identifiers are generated via truncated SHA-256 digests in `runtime_truth.core.identifiers`:

- **Entity ID:** `sha256(f"{entity_type}:{normalized_value}:{qualifier}")[:16]`
- **Event ID:** `sha256(f"{run_id}:{raw_reference}:{index}")[:16]`
- **Evidence ID:** `sha256(f"{run_id}:{collector}:{subject}")[:16]`
- **Finding ID:** `sha256(f"{run_id}:{finding_type}:{subject}")[:16]`
