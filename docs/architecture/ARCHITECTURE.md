# Runtime Truth: Architecture Specification

## Overview

Runtime Truth enforces a rigorous unidirectional pipeline that bridges the semantic gap between what software manifests declare and what executing processes perform on the host system.

```
                    USER / CLI
                        |
                        v
                   ORCHESTRATOR
                   /           \
                  v             v
        STATIC ANALYSIS   RUNTIME OBSERVATION
               |                 |
               v                 v
       DECLARED MODEL      RAW EVENTS
                                  |
                                  v
                         EVENT NORMALIZER
                                  |
                                  v
                         OBSERVED MODEL
               \                 /
                \               /
                 v             v
                  RECONCILIATION
                        |
                        v
                  FINDING ENGINE
                        |
                        v
                   EVIDENCE STORE
                        |
                        v
                  REPORT ENGINE
```

---

## Core Invariant

> **Static analysis must never directly compare itself with raw runtime events.**

Directly comparing AST imports or `requirements.txt` entries against raw `strace` or eBPF syscalls couples static heuristics to specific operating system details, breaking backend pluggability and rendering findings unexplainable.

The architecture decouples the pipeline into two decoupled pipelines:
1. **Static Analysis Pipeline:** Raw manifests and code are extracted into a normalized **Declared Model**.
2. **Runtime Observation Pipeline:** Raw system events are normalized into **Canonical Events**, aggregated into an **Observed Model**, and annotated with **Evidence**.

The **Reconciliation Engine** operates exclusively on `DeclaredModel` vs `ObservedModel`, completely oblivious to whether runtime observation was generated via `strace`, recorded logs, or future eBPF probes.

---

## Subsystem Details

### 1. Static Analysis Subsystem (`runtime_truth/static_analysis/`)

- **Interface:** `StaticParser` with `can_parse(path)` and `parse(path, run_id, project_root)`.
- **Engine:** `StaticAnalysisEngine` coordinates parsers across project files, ignoring build and environment directories (`.git`, `.venv`, `node_modules`).
- **Parsers:**
  - `PythonAstParser`: Safely walks the AST without evaluating Python code. Captures imports (`import`, `from ... import`) and static environment lookups (`os.getenv`, `os.environ[...]`).
  - `RequirementsTxtParser`: Parses pip requirement specifiers, strips comments and markers, extracts package names and version constraints.
  - `PyprojectTomlParser`: Parses PEP 621 `[project.dependencies]` and Poetry `[tool.poetry.dependencies]`.
  - `PackageJsonParser`: Parses npm `dependencies` and `devDependencies`.
  - `DockerfileParser`: Extracts `EXPOSE`, `ENV`, `CMD`, `ENTRYPOINT`, and `WORKDIR`.
  - `JsonConfigParser` / `YamlConfigParser`: Extracts network endpoints (URLs), ports, and declared environment structures.
- **Output:** `DeclaredModel` containing a collection of `DeclaredEntity` records.

### 2. Runtime Observation Subsystem (`runtime_truth/runtime/`)

- **Interface:** `RuntimeObserver` with `is_available()` and `observe(target, run_id)`.
- **Implementations:**
  - `DockerStraceObserver`: Builds or locates `runtime-truth-tracer:latest` (from `Dockerfile.tracer`), mounts the target project read-only (`:ro`), and traces child processes via `strace` using `--cap-add=SYS_PTRACE`. The host does not need `strace` installed.
  - `StraceHostObserver`: Executes commands directly on the host using `strace -f -tt -e trace=...`.
  - `OfflineLogObserver`: Reads and replays previously recorded raw strace logs. Enables deterministic testing and CI verification without root privileges or Docker.
- **Isolation Boundaries:**
  - Containers run with `--cap-add=SYS_PTRACE` (required for `ptrace` system calls), avoiding full `--privileged` mode.
  - Target files are mounted read-only (`:ro`).
  - No Docker socket or host credentials are mounted into the tracer.
- **Output:** Stream of `RawEvent` objects containing line sequences and raw payloads, and preservation of raw log in `.runtimetruth/runs/<run-id>/raw/strace.log`.

### 3. Canonical Normalization & Synthesis (`runtime_truth/observation/`)

- **Interface:** `EventNormalizer` and `ObservedModelBuilder`.
- **Normalizer (`StraceEventNormalizer`):** Maps syscall signatures (`connect`, `openat`, `execve`, `unlink`, `exit_group`) to canonical `RuntimeEventType` events with structured attributes (`destination`, `port`, `path`, `executable`, `args`).
- **Builder (`CanonicalObservedModelBuilder`):**
  - Aggregates canonical events into `ObservedEntity` records by category.
  - Synthesizes runtime dependencies from file access patterns (`site-packages/<pkg>` / `node_modules/<pkg>`).
  - Generates immutable `Evidence` records linking each event's raw reference, collector, and timestamp.
- **Output:** `ObservedModel` and `List[Evidence]`.

### 4. Reconciliation & Findings Engine (`runtime_truth/reconciliation/` & `runtime_truth/findings/`)

- **Matcher (`EntityMatcher`):** Compares declared normalized values against observed normalized values by category (`DEPENDENCY`, `NETWORK_DESTINATION`, `FILESYSTEM_PATH`, `PROCESS`, `ENVIRONMENT_VARIABLE`).
- **Discrepancy Categorization:**
  - `DEPENDENCY_DECLARED_NOT_OBSERVED`: Declared in manifests but never imported or loaded during execution.
  - `RUNTIME_DEPENDENCY_NOT_DECLARED`: Loaded from `site-packages` or runtime files without appearing in declarations.
  - `NETWORK_DECLARED_NOT_OBSERVED`: Configured external host never contacted.
  - `NETWORK_OBSERVED_NOT_DECLARED`: Outbound TCP/UDP connection observed to an undeclared address.
  - `FILESYSTEM_OBSERVED_NOT_DECLARED`: Application file accessed outside declared paths.
  - `PROCESS_OBSERVED_NOT_DECLARED`: Child executable launched that was not declared in Dockerfile CMD/ENTRYPOINT.
  - `ENVIRONMENT_OBSERVED_NOT_DECLARED`: Environment variable read via `os.environ` that was not declared.
- **Evidence Linking:** Every finding referencing runtime behavior retains the IDs of the supporting `Evidence` records.

### 5. Storage Layer (`runtime_truth/storage/`)

- **SQLite Database (`Database`):** Relational storage supporting full foreign-key cascading and indexed queries for `runs`, `declared_entities`, `runtime_events`, `observed_entities`, `evidence`, and `findings`.
- **Filesystem Artifacts (`ArtifactExporter`):** Exports each run into `.runtimetruth/runs/<run_id>/`:
  - `declared.json`: All declared entities.
  - `events.jsonl`: Line-delimited canonical runtime events.
  - `observed.json`: Synthesized observed model.
  - `findings.json`: All generated findings.
  - `report.html`: Standalone self-contained HTML report.

### 6. Reporting Subsystem (`runtime_truth/reporting/`)

- **CLI (`CliReportFormatter`):** Uses Rich for terminal tables, severity color coding, and summary panels.
- **JSON (`JsonReportGenerator`):** Machine-readable structured payload suitable for automation and CI gates.
- **HTML (`HtmlReportGenerator`):** Self-contained, responsive Jinja2 template with collapsible evidence inspection.
