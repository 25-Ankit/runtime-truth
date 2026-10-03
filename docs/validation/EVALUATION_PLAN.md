# Runtime Truth — Evaluation Plan v1.0

**Version:** 1.0
**Status:** Draft for Review
**Date:** 2026-10-03

This is a *future measurement protocol*. No numerical benchmark results exist yet and none are claimed. Results will be recorded only after controlled execution.

## Controlled evaluation cases (all use deterministic fixtures, offline replay unless stated)

1. **Exact declared/observed match** — manifests and imports fully covered by the trace; expect 0 actionable findings.
2. **Unused declared dependency** — e.g. `unused-package`; expect exactly 1 `DEPENDENCY_DECLARED_NOT_OBSERVED`.
3. **Runtime package artifact** — undeclared `site-packages` load; expect `PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED` (INFO), counted informational only.
4. **Undeclared child process** — e.g. `/usr/bin/echo`; expect 1 `PROCESS_OBSERVED_NOT_DECLARED`; target runner must not appear.
5. **Declared network destination, never contacted** — expect 1 `NETWORK_DECLARED_NOT_OBSERVED`.
6. **Uncorrelated network IP** — numeric IP observed with hostname declared, no DNS evidence; expect 1 `NETWORK_IDENTITY_UNCORRELATED`, never `NETWORK_OBSERVED_NOT_DECLARED`.
7. **Expected workspace file activity** — `/app/app.py`, `/app/config.json` under declared `WORKDIR`; expect 0 filesystem findings.
8. **Unexpected file activity** — e.g. `/app/secret.key` (not a project source); expect 1 `FILESYSTEM_OBSERVED_NOT_DECLARED`.
9. **Repeated runtime execution** — same fixture + same log twice; expect byte-identical canonical findings (modulo run IDs/timestamps).
10. **Behavioral change across versions** — fixture v1 vs v2 with one added import + one new connection; expect the delta to appear exactly in `diff` output.

## Metrics (definitions; values to be measured later)

- **Declaration extraction accuracy** — per-parser precision/recall of entities vs hand-annotated fixture manifests.
- **Event normalization accuracy** — fraction of trace lines mapped to the correct `RuntimeEventType` + attributes on annotated logs.
- **Reconciliation precision** — fraction of emitted actionable findings that match hand-labeled ground truth per case.
- **False positive rate** — actionable findings emitted where ground truth expects none (target: 0 on cases 1, 7, 9).
- **False negative rate** — expected findings missing (target: 0 on cases 2–6, 8, 10).
- **Trace completeness** — canonical events / non-empty raw lines (informational; loader noise documented, not penalized).
- **Evidence linkage correctness** — fraction of runtime-derived findings whose `evidence_ids` resolve to `Evidence` records whose `raw_reference` exists verbatim in `raw/strace.log` (target: 100%).
- **Runtime overhead** — wall-clock `strace`-vs-native execution delta on the demo fixture (method: 5 timed runs each, report median + range).
- **Run reproducibility** — findings equality across 3 reruns per mode (static/offline/docker-image-cached).

## Method notes

- Ground truth is hand-labeled per fixture by the evaluator; fixtures live under `cases/` or `tests/fixtures/`.
- Overhead and reproducibility runs use the cached tracer image (no rebuild timing included).
- Any metric that cannot be measured with the current fixture corpus is reported as `NOT_MEASURED`, never interpolated.
