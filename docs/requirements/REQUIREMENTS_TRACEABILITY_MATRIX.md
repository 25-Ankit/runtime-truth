# Runtime Truth — Requirements Traceability Matrix v1.0

**Version:** 1.0
**Status:** Baseline
**Date:** 2026-10-03

Format: Requirement → Architecture component → Implementation file/module → Test(s) → Evidence → Status.
Test names are actual files in `tests/`; no test names are invented.

| Req | Summary | Architecture | Implementation | Tests | Evidence | Status |
|---|---|---|---|---|---|---|
| TR-001 | Decoupled models + reconciliation boundary | Orchestrator / Reconciliation | `runtime_truth/reconciliation/engine.py`, `runtime_truth/static_analysis/base.py`, `runtime_truth/observation/base.py` | `tests/unit/test_reconciliation.py`, `tests/unit/test_matcher.py` | Findings reference declared+observed states, never raw syscalls | IMPLEMENTED |
| TR-002 | Orchestrator pipeline | Orchestrator | `runtime_truth/orchestrator/runner.py` | `tests/integration/test_orchestrator.py`, `tests/integration/test_docker_observer.py` | `Run` status transitions; artifact dirs per run | IMPLEMENTED |
| TR-003 | Python AST + stdlib tagging | Static Analysis | `runtime_truth/static_analysis/parsers/python_ast.py` | `tests/unit/test_static_parsers.py::test_python_ast_parser`, `tests/unit/test_reconciliation.py::test_reconciliation_stdlib_separation` | `metadata.is_stdlib` on entities | IMPLEMENTED |
| TR-004 | requirements.txt | Static Analysis | `…/parsers/requirements.py` | `test_static_parsers.py::test_requirements_txt_parser` | Line-numbered entities | IMPLEMENTED |
| TR-005 | pyproject.toml | Static Analysis | `…/parsers/pyproject.py` | `test_static_parsers.py::test_pyproject_toml_parser` | PEP 621 + Poetry entities | IMPLEMENTED |
| TR-006 | package.json | Static Analysis | `…/parsers/package_json.py` | `test_static_parsers.py::test_package_json_parser` | npm-tagged entities | IMPLEMENTED |
| TR-007 | Dockerfile | Static Analysis | `…/parsers/dockerfile.py` | `test_static_parsers.py::test_dockerfile_parser` | Ports/env/process/path entities | IMPLEMENTED |
| TR-008 | JSON/YAML config | Static Analysis | `…/parsers/config_parser.py` | `test_static_parsers.py::test_config_parsers` | URL/port/env entities | IMPLEMENTED |
| TR-009 | Docker tracer env | Runtime Observation | `runtime_truth/runtime/docker/Dockerfile.tracer`, `runtime_truth/runtime/observers.py::DockerStraceObserver` | `tests/integration/test_docker_observer.py`, `tests/unit/test_docker_observer.py` | `runtime-truth-tracer:latest`; `:ro` mount; `SYS_PTRACE` | IMPLEMENTED |
| TR-010 | Three strace backends | Runtime Observation | `runtime_truth/runtime/observers.py` | `test_docker_observer.py`, `test_orchestrator.py`, `test_cli.py` | `strace_host`/`strace_docker`/`strace_offline` collectors | IMPLEMENTED |
| TR-011 | Canonical events | Normalizer | `runtime_truth/observation/normalizer.py` | `tests/unit/test_normalizer.py` | `events.jsonl` records | IMPLEMENTED |
| TR-012 | Raw evidence preservation | Evidence Store / Storage | `runtime_truth/storage/artifacts.py`, `runtime_truth/evidence/store.py` | `test_docker_observer.py::test_raw_evidence_artifact_paths`, `test_storage.py::test_artifact_exporter` | `raw/strace.log` + `raw_reference` fields | IMPLEMENTED |
| TR-013 | Target vs child process | Observed Model / Reconciliation | `runtime_truth/observation/builder.py`, `runtime_truth/reconciliation/engine.py` | `test_reconciliation.py::test_reconciliation_target_process_and_workspace_activity`, `test_reporting.py::test_target_process_not_emitted…` | `is_target_process` attrs in `observed.json`; no `TARGET_PROCESS` in `findings.json` | IMPLEMENTED |
| TR-014 | Filesystem semantics | Observed Model / Reconciliation | `builder.py` (prefix filter), `reconciliation/engine.py` (workspace suppression) | `test_reconciliation_target_process_and_workspace_activity`, `test_reconciliation_discrepancies` (`/app/secret.key` positive) | `observed.json` vs `findings.json` comparison | IMPLEMENTED |
| TR-015 | Network w/o DNS | Observed Model / Reconciliation | `reconciliation/engine.py` (`is_ip` + `NETWORK_IDENTITY_UNCORRELATED`) | `test_reconciliation_discrepancies`, live Docker run | `NETWORK_IDENTITY_UNCORRELATED` record with hostname context | PARTIALLY_IMPLEMENTED |
| TR-016 | Domain models | Core | `runtime_truth/core/models.py`, `enums.py`, `identifiers.py` | `test_core_models.py`, `test_identifiers.py` | Schema-validated JSON artifacts | IMPLEMENTED |
| TR-017 | SQLite + artifacts | Storage | `runtime_truth/storage/database.py`, `repositories.py`, `artifacts.py` | `test_storage.py`, `test_orchestrator.py` | DB rows + 6-file run dirs | IMPLEMENTED |
| TR-018 | 3-channel / 3-way reporting | Reporting / Findings | `runtime_truth/reporting/*`, `runtime_truth/findings/engine.py` | `test_reporting.py` (incl. `test_finding_summary_separation`), `test_cli.py` | CLI/JSON/HTML summaries agree | IMPLEMENTED |
| TR-019 | Container safety | Runtime / Threat Model | `observers.py::build_docker_command` | `test_docker_observer.py::test_docker_observer_command_construction_*` | Command assertions (`--cap-add`, `:ro`, no `--privileged`/socket) | IMPLEMENTED |
| TR-020 | Offline determinism | Runtime / Storage | `observers.py::OfflineLogObserver`, `cases/demo-app/recorded_strace.log` | `test_orchestrator.py::test_orchestrator_with_offline_strace_replay` | Rerun-equal findings | IMPLEMENTED |
| TR-021 | Error handling | Orchestrator / Core errors | `runner.py`, `core/errors.py` | Negative paths in `test_cli.py`, `test_storage.py` | Exit codes + `RunStatus.FAILED` | IMPLEMENTED |
| TR-022 | Pluggable interfaces | All boundaries | `runtime/base.py`, `observation/base.py`, `static_analysis/base.py` | Architectural (interface conformance via observer/parser tests) | eBPF-ready contract | IMPLEMENTED |
| TR-023 | DNS correlation | — (future) | — | — | — | PLANNED |
| TR-024 | Lockfiles/resolution | — (future) | — | — | — | PLANNED |
| TR-025 | Behavioral baselines | CLI (scaffold) | `runtime_truth/cli/main.py` (`baseline`/`diff`) | `test_cli.py::test_cli_scan_and_report_and_diff` | Baseline JSON snapshots | PARTIALLY_IMPLEMENTED |
| TR-026 | Drift detection | — (future) | enum value `BEHAVIORAL_DRIFT` reserved | — | — | PLANNED |
| TR-027 | eBPF backends | — (future) | — | — | — | PLANNED |
| TR-028–031 | Semantic rules (stdlib, artifact, target/child, 3-way) | Parsers/Reconciliation/Reporting | (same files as TR-003/011/013/014/018) | (same tests) | Reference run 3/10/1 | IMPLEMENTED |
| TR-032–035 | AI / K8s / cloud / dashboard | — | — | — | — | OUT_OF_SCOPE |
