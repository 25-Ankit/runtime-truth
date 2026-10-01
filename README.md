# Runtime Truth

> **"Declared Software Model vs Observed Runtime Behavior"**

Runtime Truth is an evidence-driven, local-first developer verification system that compares what an application declares it needs and does (in configuration, manifests, and source code) with what it actually does at runtime.

---

## The Problem

Modern software projects declare their requirements across multiple disconnected artifacts: `requirements.txt`, `pyproject.toml`, `package.json`, `Dockerfile`, and config files. However, what runs in production often diverges:
- Declared dependencies may never actually be imported or used (bloat).
- Undeclared transitive or dynamic libraries may execute without documentation.
- Applications may contact unexpected external network destinations.
- Processes and filesystem paths may be accessed without declaration.

Runtime Truth formalizes and automates the comparison between declared declarations and observed runtime executions.

---

## Core Principle

```
        Declared Model
              VS
     Observed Runtime Model
              ↓
        Reconciliation
              ↓
    Evidence-backed Findings
```

### Hard Architectural Rule

**Static analysis must never directly compare itself with raw runtime events.**

Instead, the system enforces a strict pipeline:
1. **Static Sources** $\rightarrow$ **Declared Model**
2. **Runtime Sources** $\rightarrow$ **Raw Events** $\rightarrow$ **Canonical Events** $\rightarrow$ **Observed Model**
3. **Declared Model + Observed Model** $\rightarrow$ **Reconciliation** $\rightarrow$ **Evidence-backed Findings**

Every finding links to verifiable evidence records containing timestamps, collectors, and raw log references.

---

## What v0.1 Implements

- **Domain Models & Enums:** Deterministic Pydantic schemas for `Run`, `DeclaredEntity`, `RuntimeEvent`, `ObservedEntity`, `Evidence`, and `Finding`.
- **Static Analysis Engine:**
  - Python AST parser: imports (`import`, `from ... import`), environment variable calls (`os.getenv`, `os.environ`).
  - Python manifest parsers: `requirements.txt` (versions, markers, extras) and `pyproject.toml` (PEP 621, Poetry).
  - Node.js manifest parser: `package.json` (`dependencies`, `devDependencies`).
  - Container parser: `Dockerfile` (`EXPOSE`, `ENV`, `CMD`/`ENTRYPOINT`, `WORKDIR`, `VOLUME`).
  - Configuration parsers: JSON and YAML parsers extracting network URLs, ports, and environment mappings.
- **Runtime Observation & Normalization:**
  - Syscall parsing for `strace` output: `connect`, `openat`/`open`, `execve`, `unlink`/`unlinkat`, `exit_group`.
  - Canonical event normalization hiding collector details.
  - Pluggable observation backends: `StraceHostObserver`, `DockerStraceObserver`, and `OfflineLogObserver` (for deterministic replay without root).
- **Observed Model Synthesis:** Aggregation of canonical events into observed entities and evidence linking.
- **Reconciliation Engine:** Deterministic category-based matching (dependencies, network, filesystem, process, environment).
- **Finding Generation:** Specific finding types (`DEPENDENCY_DECLARED_NOT_OBSERVED`, `RUNTIME_DEPENDENCY_NOT_DECLARED`, `NETWORK_DECLARED_NOT_OBSERVED`, `NETWORK_OBSERVED_NOT_DECLARED`, `FILESYSTEM_OBSERVED_NOT_DECLARED`, `PROCESS_OBSERVED_NOT_DECLARED`, `ENVIRONMENT_OBSERVED_NOT_DECLARED`).
- **Persistence & Artifacts:**
  - SQLite database storing runs, entities, events, evidence, and findings.
  - Filesystem run export in `.runtimetruth/runs/<run_id>/` containing `declared.json`, `events.jsonl`, `observed.json`, `findings.json`, and `report.html`.
- **Reporting:**
  - Terminal CLI summary with rich formatted tables and severity badges.
  - Structured JSON export (`--json`).
  - Responsive standalone HTML reports with evidence inspection.
- **CLI Commands:** `scan`, `report`, `diff`, `baseline create`.
- **Controlled Demo Fixture:** `cases/demo-app/` with reproducible offline strace logs.

---

## What is NOT Implemented (v0.1 Boundaries)

- **No AI / LLM reasoning:** Analysis is strictly deterministic and based on structural comparisons.
- **No cloud dependencies:** Everything executes locally and writes to local SQLite/filesystem storage.
- **No Kubernetes integrations:** Local Linux processes and Docker containers only.
- **No web dashboards / React:** Self-contained static HTML and CLI outputs only.
- **No eBPF kernel probes:** Currently planned for future observation backends; strace is the initial syscall backend.
- **Not a security vulnerability scanner:** Runtime Truth reports structural discrepancies and evidence. Interpretation remains with the developer.
- **No full dependency solver:** Manifests and imports are extracted safely without resolving remote dependency graphs or wheel resolution.

---

## Installation

### Prerequisites
- Linux (x86_64 / aarch64)
- Python 3.12+
- Optional for live runtime tracing: `strace` or `docker`

### Install in Virtual Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Runtime Truth in editable mode
pip install -e .
```

Verify installation:
```bash
runtime-truth --help
```

---

## Local Usage

### 1. Scan a Project (Static Only)

```bash
runtime-truth scan /path/to/project
```

### 2. Scan with Offline Runtime Syscall Replay

```bash
runtime-truth scan cases/demo-app --mode offline_events --offline-log cases/demo-app/recorded_strace.log
```

Output formatted JSON report:
```bash
runtime-truth scan cases/demo-app --mode offline_events --offline-log cases/demo-app/recorded_strace.log --json
```

### 3. Inspect Previous Run Reports

```bash
# Terminal summary
runtime-truth report <run-id>

# JSON export
runtime-truth report <run-id> --format json

# HTML report
runtime-truth report <run-id> --format html > report.html
```

### 4. Create Baseline and Compare Runs (Diff)

```bash
# Establish run as accepted baseline
runtime-truth baseline create <run-id> --name v1.0

# Compare two runs
runtime-truth diff <run-id-a> <run-id-b>
```

---

## Testing

Run the full pytest suite:

```bash
pytest -v
```

All unit and integration tests execute deterministically without external network or root access.

---

## Roadmap

- **v0.2:** Containerized live strace runner with Docker socket integration (`DockerStraceObserver`).
- **v0.3:** Support for language package manager locks (`poetry.lock`, `package-lock.json`, `pnpm-lock.yaml`).
- **v0.4:** eBPF-based socket and syscall observation backend (`ebpf_observer`) adhering to the same canonical event contract.
- **v0.5:** CI/CD GitHub Action and exit code gates based on discrepancy thresholds.
