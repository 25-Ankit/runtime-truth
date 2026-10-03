# Runtime Truth — Test and Validation Plan v1.0

**Version:** 1.0
**Status:** Baseline
**Date:** 2026-10-03
**Baseline result:** 47 tests passed (latest verified implementation state). No additional results are claimed here.

## Test inventory (actual files)

- `tests/unit/test_core_models.py` — model defaults, serialization round-trips, enum validation errors.
- `tests/unit/test_identifiers.py` — determinism of `ent_`/`evt_`/`evi_`/`fnd_`/`run_` IDs.
- `tests/unit/test_static_parsers.py` — requirements, pyproject, package.json, Dockerfile, Python AST (incl. env vars), JSON/YAML config.
- `tests/unit/test_normalizer.py` — `connect`/`openat`/`execve` normalization, builder synthesis (network/dependency/filesystem/process + evidence linkage).
- `tests/unit/test_matcher.py` — declared/observed matching by normalized value.
- `tests/unit/test_reconciliation.py` — exact match (0 findings), 6-way discrepancy mix, stdlib separation, target-process + workspace suppression.
- `tests/unit/test_storage.py` — run CRUD + status updates, entity/event/observed/evidence/finding round-trips, artifact exporter layout.
- `tests/unit/test_reporting.py` — JSON/HTML generation, three-way summary separation, target-process non-emission with observed-model preservation.
- `tests/unit/test_docker_observer.py` — observer config defaults, `docker run` command construction (ro/rw), raw-evidence artifact paths.
- `tests/integration/test_orchestrator.py` — static-only run, offline-replay run (findings + all 5 artifacts).
- `tests/integration/test_docker_observer.py` — availability, image ensure, live execution, Docker-mode orchestration (raw evidence + 3-way summary), CLI `--mode docker --json`.
- `tests/integration/test_cli.py` — `--help`, `--version`, scan→report→baseline→diff end-to-end.

## Acceptance criteria per subsystem

- **Unit:** each parser/normalizer/matcher/builder/summarizer behaves per its docstring on fixtures; no network, no Docker, no root required.
- **Integration:** orchestrator completes `RunStatus.COMPLETED` on `cases/demo-app` in static, offline, and Docker modes with artifacts verified on disk.
- **Docker:** skipped with explicit reason (`is_docker_available() == False`) when the daemon is unreachable — never silent-passed. In this environment: executed (daemon responsive).
- **Offline replay:** identical findings across reruns from `recorded_strace.log`.
- **CLI:** exit code 0 on happy paths, exit code 1 with error text on invalid mode / unknown run.
- **Storage:** conflict-safe upserts preserve cascade children (regression-guarded after the `INSERT OR REPLACE` incident).
- **Reporting:** CLI/JSON/HTML agree on the three-way counts; HTML renders all three sections with evidence drill-down.
- **Regression:** all 47 pass; any new phase must keep them green.

## Negative controls

- Unknown run ID → `report`/`baseline create` fail with exit 1, no artifact written.
- Missing log file → `OfflineLogObserver.observe` raises `ObservationError`.
- Docker daemon down → `DockerStraceObserver.is_available()` False; orchestrator raises instead of inventing events.
- Unparsable source file → parser returns `[]`, scan continues.
- Failed `execve` (`ENOENT` path probes) → no `PROCESS_SPAWN` event.

## Determinism tests

- Identifier determinism (same inputs → same IDs; qualifier-sensitive).
- Offline replay rerun equality (canonical events, observed entities, findings).
- Findings ordering stable per reconciliation category order.

## Evidence provenance tests

- Every runtime-derived finding carries non-empty `evidence_ids`; every `Evidence` carries `raw_reference`/`raw_evidence` present verbatim in `raw/strace.log` (manually verified on the reference Docker run for `NETWORK_IDENTITY_UNCORRELATED 93.184.216.34`).
- `observed.json` retains target-process attributes (`is_target_process`, `process_role`) while `findings.json` contains no `TARGET_PROCESS` record.
