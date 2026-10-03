# Runtime Truth — Technical Requirements Document v1.0

**Version:** 1.0
**Status:** Baseline
**Date:** 2026-10-03
**Implementation baseline:** commit `6ed610b` (Phase 1 + semantic cleanup, 47 tests passing).

Status values: `IMPLEMENTED` | `PARTIALLY_IMPLEMENTED` | `PLANNED` | `OUT_OF_SCOPE`.
Priorities: `P0` (correctness/safety-critical) | `P1` (core function) | `P2` (robustness/extensibility).

---

## A. Architecture

### TR-001 — Decoupled declared vs observed models with reconciliation boundary
- **Requirement:** Static analysis shall produce a `DeclaredModel`; runtime observation shall produce canonical `RuntimeEvent`s and an `ObservedModel`; only `ReconciliationEngine` (`runtime_truth/reconciliation/engine.py`) may compare the two models. Static parsers shall never consume raw runtime events; observers/normalizers shall never consume manifests.
- **Rationale:** Preserves backend pluggability (strace today, eBPF later) and keeps findings explainable.
- **Priority:** P0. **Status:** IMPLEMENTED (`runtime_truth/static_analysis/base.py`, `runtime_truth/observation/`, `runtime_truth/reconciliation/`).

### TR-002 — Orchestrator pipeline
- **Requirement:** `Orchestrator.execute()` (`runtime_truth/orchestrator/runner.py`) shall run static analysis → observation/normalization/synthesis → reconciliation → report/export → SQLite persistence in one deterministic flow, recording `Run` status transitions (`pending`/`running`/`completed`/`failed`) and raising `ObservationError` when a selected observer is unavailable.
- **Rationale:** Single reproducible entry point for CLI, tests, and CI.
- **Priority:** P0. **Status:** IMPLEMENTED.

## B. Static analysis

### TR-003 — Python AST import and environment extraction
- **Requirement:** `PythonAstParser` shall extract `import`/`from…import` statements with file/line/column provenance and tag standard-library modules via `sys.stdlib_module_names` (`metadata.is_stdlib`), plus static `os.getenv`/`os.environ` accesses, without executing project code.
- **Rationale:** Safe declaration source; stdlib tagging prevents stdlib false positives downstream.
- **Priority:** P1. **Status:** IMPLEMENTED (`runtime_truth/static_analysis/parsers/python_ast.py`).

### TR-004 — requirements.txt parsing
- **Requirement:** Parse package names, version specifiers, extras, markers, and line numbers; ignore comments, pip flags, and empty lines.
- **Rationale:** Primary Python declaration source for the demo and common projects.
- **Priority:** P1. **Status:** IMPLEMENTED (`…/parsers/requirements.py`).

### TR-005 — pyproject.toml parsing
- **Requirement:** Parse PEP 621 `[project.dependencies]`, `[project.optional-dependencies]`, and Poetry `[tool.poetry.dependencies]` (excluding the `python` constraint).
- **Rationale:** Covers modern Python packaging layouts.
- **Priority:** P1. **Status:** IMPLEMENTED (`…/parsers/pyproject.py`).

### TR-006 — package.json parsing
- **Requirement:** Parse `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies` with npm ecosystem tagging.
- **Rationale:** Minimal Node.js declaration support for polyglot projects.
- **Priority:** P2. **Status:** IMPLEMENTED (`…/parsers/package_json.py`).

### TR-007 — Dockerfile parsing
- **Requirement:** Extract `EXPOSE` (ports), `ENV` (variables + defaults), `CMD`/`ENTRYPOINT` (processes), `WORKDIR`/`VOLUME` (filesystem paths) with line provenance.
- **Rationale:** Container-declared runtime surface; `WORKDIR` doubles as workspace-activity reference.
- **Priority:** P1. **Status:** IMPLEMENTED (`…/parsers/dockerfile.py`).

### TR-008 — JSON/YAML config extraction
- **Requirement:** Safely (`json` + `yaml.safe_load`) extract HTTP(S) URL hosts as network destinations, `port`-family keys as ports, and `env`-family mappings as environment variables; never execute config content.
- **Rationale:** Declared network/port/env surface for reconciliation.
- **Priority:** P1. **Status:** IMPLEMENTED (`…/parsers/config_parser.py`).

## C. Runtime

### TR-009 — Docker tracer execution environment
- **Requirement:** `DockerStraceObserver` shall build or locate `runtime-truth-tracer:latest` from `runtime_truth/runtime/docker/Dockerfile.tracer` (Python 3.12-slim + `strace`), mount the target directory read-only at `/app` (`:ro`), run with `--cap-add=SYS_PTRACE` and `--rm`, and never use `--privileged`, never mount the Docker socket, never expose host credentials.
- **Rationale:** Reproducible observation without host `strace`; least-privilege isolation.
- **Priority:** P0. **Status:** IMPLEMENTED (`runtime_truth/runtime/observers.py`, `runtime_truth/runtime/docker/`).

### TR-010 — strace observation across three backends
- **Requirement:** `StraceHostObserver` (host `strace -f -tt`), `DockerStraceObserver` (containerized `strace`), and `OfflineLogObserver` (recorded-log replay) shall all implement `RuntimeObserver.observe()` returning `RawEvent` lists with collector labels `strace_host` / `strace_docker` / `strace_offline`.
- **Rationale:** Live, isolated, and deterministic observation paths behind one contract.
- **Priority:** P0. **Status:** IMPLEMENTED.

### TR-011 — Canonical RuntimeEvent contract
- **Requirement:** `StraceEventNormalizer` shall map `connect` (IPv4/IPv6), `openat`/`open`, `execve`, `unlink`/`unlinkat`, `exit_group`/`exit` to `RuntimeEventType` events with structured attributes, drop `<unfinished>`/`resumed>` fragments, and drop failed `execve` path probes (`= -1 …`) so PATH searches never become process spawns.
- **Rationale:** Observer details stay hidden from reconciliation; future backends reuse the contract.
- **Priority:** P0. **Status:** IMPLEMENTED (`runtime_truth/observation/normalizer.py`).

### TR-012 — Raw evidence preservation
- **Requirement:** Every observation run shall preserve the complete raw trace at `.runtimetruth/runs/<run-id>/raw/strace.log` via `ArtifactExporter(..., raw_trace_content=...)`, and every `Evidence` record shall carry the verbatim `raw_reference` line.
- **Rationale:** Enables the finding → entity → event → raw-line provenance chain.
- **Priority:** P0. **Status:** IMPLEMENTED (`runtime_truth/storage/artifacts.py`, `runtime_truth/orchestrator/runner.py`).

### TR-013 — Process observation semantics
- **Requirement:** The first `PROCESS_SPAWN` per run shall be marked `is_target_process=True` / `process_role=TARGET_PROCESS` in the `ObservedModel` and excluded from findings; subsequent spawns (e.g. `/usr/bin/echo`) are `CHILD_PROCESS` candidates for `PROCESS_OBSERVED_NOT_DECLARED`.
- **Rationale:** Eliminates the target-runner false positive while keeping child-process detection.
- **Priority:** P1. **Status:** IMPLEMENTED (`runtime_truth/observation/builder.py`, `runtime_truth/reconciliation/engine.py`).

### TR-014 — Filesystem observation semantics
- **Requirement:** System prefixes (`/proc/`, `/sys/`, `/dev/`, `/lib/`, `/lib64/`, `/usr/`, `/etc/`, `/bin/`, `/sbin/`) shall not become `FILESYSTEM_PATH` entities; accesses under a declared workspace directory matching project source filenames (e.g. `/app/app.py`, `/app/config.json` under `WORKDIR /app`) shall be treated as expected workspace activity and suppressed from findings.
- **Rationale:** Suppresses interpreter/loader noise and ordinary source reads.
- **Priority:** P1. **Status:** IMPLEMENTED.

### TR-015 — Network observation without DNS correlation
- **Requirement:** Observed numeric IPs with no exact declared match shall be emitted as `NETWORK_IDENTITY_UNCORRELATED` (MEDIUM) whenever declared hostnames exist, with an explanation citing missing DNS interception; exact-match logic otherwise applies. No IP→hostname claim shall be made.
- **Rationale:** Honest handling of the hostname/IP gap pending Phase 2.
- **Priority:** P1. **Status:** PARTIALLY_IMPLEMENTED (observation + honest classification done; correlation itself is Phase 2, TR-023).

## D. Data

### TR-016 — Core domain models
- **Requirement:** Pydantic v2 models `Run`, `DeclaredEntity` (+`SourceLocation`), `RuntimeEvent`, `ObservedEntity`, `Evidence`, `Finding`, `DeclaredModel`, `ObservedModel` per `docs/architecture/DATA_MODEL.md`, with deterministic SHA-256-truncated IDs (`ent_`/`evt_`/`evi_`/`fnd_`) and `ObservedEntityType.PACKAGE_ARTIFACT` distinct from `DEPENDENCY`.
- **Rationale:** Stable, serializable, testable contracts across the pipeline.
- **Priority:** P0. **Status:** IMPLEMENTED (`runtime_truth/core/`).

## E. Storage

### TR-017 — SQLite storage and run artifacts
- **Requirement:** Versioned SQLite schema (`runs`, `declared_entities`, `runtime_events`, `observed_entities`, `evidence`, `findings`) with conflict-safe upserts preserving cascade relationships, plus per-run artifact directories (`declared.json`, `raw/strace.log`, `events.jsonl`, `observed.json`, `findings.json`, `report.html`).
- **Rationale:** Queryable history + filesystem reproducibility without external services.
- **Priority:** P1. **Status:** IMPLEMENTED (`runtime_truth/storage/`).

## F. Reporting

### TR-018 — Three-channel reporting with three-way summary
- **Requirement:** CLI (`CliReportFormatter`), JSON (`JsonReportGenerator`), and HTML (`HtmlReportGenerator`) reports shall present `actionable_findings` / `informational_observations` / `unresolved_correlations` (never a single `Total Discrepancies` metric); package artifacts count only as informational; `TARGET_PROCESS` is observed-model-only. Finding classification sets live in `runtime_truth/findings/engine.py`.
- **Rationale:** Prevents informational runtime facts from inflating discrepancy counts.
- **Priority:** P1. **Status:** IMPLEMENTED (`runtime_truth/reporting/`, `runtime_truth/findings/`).

## G. Safety

### TR-019 — Container safety constraints
- **Requirement:** No `--privileged`, no Docker socket mount, read-only target mounts, no host credential exposure, no host filesystem writes outside explicit mounts, no fabricated runtime evidence (unimplemented backends raise `ObservationError`, never synthetic events).
- **Rationale:** Documented least-privilege boundaries; the tracer is an observation environment, not a proven sandbox.
- **Priority:** P0. **Status:** IMPLEMENTED (enforced in `DockerStraceObserver.build_docker_command`; documented in ARCHITECTURE.md and Threat Model v1.0).

## H. Reliability

### TR-020 — Deterministic offline replay and reproducibility
- **Requirement:** `OfflineLogObserver` + `cases/demo-app/recorded_strace.log` shall reproduce identical canonical findings without Docker or root; a complete run shall be reproducible from stored SQLite + artifact files.
- **Rationale:** CI determinism and auditability.
- **Priority:** P1. **Status:** IMPLEMENTED.

### TR-021 — Error handling
- **Requirement:** Missing project paths, unparsable files (safe skip), unavailable Docker daemon / missing `strace`, and container timeouts shall surface as typed errors (`ObservationError`, `StaticAnalysisError`/`ParserError`, `StorageError`) and `RunStatus.FAILED`, never as silent success or invented data.
- **Rationale:** Fail-loud behavior required for a verification tool.
- **Priority:** P0. **Status:** IMPLEMENTED.

## I. Extensibility

### TR-022 — Pluggable observer/normalizer interfaces
- **Requirement:** `RuntimeObserver`, `EventNormalizer`, `ObservedModelBuilder`, `StaticParser`, `ReconciliationEngine`, `EvidenceStore`, `ReportGenerator` abstractions shall allow new backends (e.g. eBPF) to emit the existing canonical event types without modifying reconciliation logic.
- **Rationale:** Future backends must not rewrite the core.
- **Priority:** P2. **Status:** IMPLEMENTED (`runtime/base.py`, `observation/base.py`, `static_analysis/base.py`).

## J. Planned (not implemented — see TDP v1.0)

### TR-023 — DNS resolution / network identity correlation (Phase 2)
- **Requirement (future):** Correlate observed numeric IPs to declared hostnames via intercepted DNS evidence. **Priority:** P1. **Status:** PLANNED. No DNS interception exists today.

### TR-024 — Lockfile and dependency resolution (Phase 3)
- **Requirement (future):** Parse `poetry.lock` / `package-lock.json` / `pnpm-lock.yaml` and resolve direct-vs-transitive relationships so package artifacts can be attributed. **Priority:** P1. **Status:** PLANNED. Today artifacts carry `observation_type=observed_package_artifact` with relationship explicitly unverified.

### TR-025 — Behavioral baselines (Phase 4)
- **Requirement (future):** Accepted-behavior baseline model with comparison semantics. **Priority:** P2. **Status:** PARTIALLY_IMPLEMENTED — `baseline create` snapshots findings JSON and `diff` compares runs (run-compare scaffolding exists); accepted-behavior modeling and drift detection do not.

### TR-026 — Behavioral drift detection (Phase 5)
- **Requirement (future):** Detect drift across versions/runs. **Priority:** P2. **Status:** PLANNED (`FindingType.BEHAVIORAL_DRIFT` reserved in enum only).

### TR-027 — Additional runtime observation backends (Phase 6)
- **Requirement (future):** eBPF or equivalent backends emitting the unchanged canonical contract. **Priority:** P2. **Status:** PLANNED.

## K. Out of scope (never planned)

### TR-028…TR-031 — Implemented semantic rules (reference)
- TR-028 stdlib separation, TR-029 package-artifact-vs-dependency distinction, TR-030 target-vs-child process distinction, TR-031 actionable/informational/unresolved reporting separation. **Priority:** P1. **Status:** IMPLEMENTED (covered by TR-003/011/013/014/015/018; listed here for traceability).

### TR-032 — AI/LLM reasoning — **OUT_OF_SCOPE**.
### TR-033 — Kubernetes integration — **OUT_OF_SCOPE**.
### TR-034 — Cloud services — **OUT_OF_SCOPE**.
### TR-035 — Web dashboard — **OUT_OF_SCOPE**.

---

**Counts:** 35 requirements — IMPLEMENTED 25 · PARTIALLY_IMPLEMENTED 2 (TR-015, TR-025) · PLANNED 4 (TR-023, TR-024, TR-026, TR-027) · OUT_OF_SCOPE 4 (TR-032…TR-035).
