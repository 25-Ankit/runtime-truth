# Runtime Truth — Technical Development Plan v1.0

**Version:** 1.0
**Status:** Baseline
**Date:** 2026-10-03

This plan records completed work precisely and scopes future work without implementing it.

---

## Phase 0 — Foundation — COMPLETE

- **Objective:** Establish the clean foundation and data contracts: domain models, storage, static analyzers, canonical events, reconciliation, reporting, CLI, demo fixture, tests, docs.
- **Scope delivered:** `runtime_truth/core|static_analysis|runtime|observation|reconciliation|findings|evidence|storage|reporting|config|orchestrator|cli`, `cases/demo-app`, 34 initial tests, README + architecture/data-model docs.
- **Dependencies:** None (greenfield).
- **Tests:** Unit (models, identifiers, parsers, normalizer, matcher, reconciliation, storage, reporting) + integration (orchestrator static/offline, CLI scan/report/diff/baseline).
- **Acceptance:** 34/34 passing; CLI smoke (`--help`, scan fixture) green.
- **Exit criteria met:** Yes — checkpoint `70bbebb`.
- **Risks encountered:** SQLite `INSERT OR REPLACE` + `ON DELETE CASCADE` cascade-delete hazard and `:memory:` connection-per-session data loss; both fixed with conflict-safe upserts and a persistent in-memory connection.
- **Excluded:** Docker live observation, DNS, lockfiles, eBPF, baselines/drift, AI, cloud, dashboard.

## Phase 1 — Containerized Runtime Observation — COMPLETE

- **Objective:** Reproducible Docker-based tracing so the host never needs `strace`.
- **Scope delivered:** `runtime_truth/runtime/docker/Dockerfile.tracer` (`runtime-truth-tracer:latest`), `DockerStraceObserver` (availability check, image build-or-locate, read-only mount, `--cap-add=SYS_PTRACE`, raw-trace capture), `raw/strace.log` preservation in artifacts + `OrchestrationResult.raw_trace_path`, `RuntimeMode.DOCKER` + `--mode docker` aliases, demo-app activity simulation (package imports, `echo` child, short-timeout socket attempt).
- **Dependencies:** Docker daemon; `python:3.12-slim` base image at build time.
- **Tests:** 9 new tests (observer config/command/raw-paths unit; availability/image/live-execution/orchestrator/CLI integration) — 43/43 with foundation.
- **Acceptance:** Live `scan cases/demo-app --mode docker` produces raw evidence + canonical events + observed model + findings + HTML/JSON reports.
- **Exit criteria met:** Yes — checkpoint `6ed610b`.
- **Risks encountered:** Tracer `pip install` of intentionally-fake `unused-package` fails by design (handled: tracer pre-installs only real deps); real-trace volume (hundreds of events) required stdlib/system-path noise suppression (deferred to cleanup below).
- **Excluded:** DNS interception, lockfile parsing, eBPF, baselines, drift, AI, cloud, dashboard.

## Phase 1 semantic/reporting cleanup — COMPLETE

- **Objective:** Remove five false-positive classes without architecture redesign.
- **Scope delivered:** stdlib tagging/filtering (`is_stdlib`), `PACKAGE_ARTIFACT` entity + `PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED` (INFO), target-process exclusion from findings (kept in observed model), workspace-activity suppression, `NETWORK_IDENTITY_UNCORRELATED` (MEDIUM), three-way reporting (Actionable/Informational/Unresolved) across CLI/JSON/HTML.
- **Tests:** 2 new reconciliation tests + 2 new reporting-semantics tests — 47/47.
- **Acceptance:** Live Docker reference 3 actionable / 10 informational / 1 unresolved; no `Total Discrepancies` string in code.
- **Exit criteria met:** Yes (verified, uncommitted working tree at pack creation).

## Phase 2 — DNS Resolution / Network Identity Correlation (PLANNED)

- **Objective:** Correlate observed numeric IPs to declared hostnames using intercepted DNS evidence.
- **Scope:** Capture `getaddrinfo`/resolver syscalls or DNS socket traffic in the tracer; new canonical event data (query → answer mapping); resolver-aware matcher replacing blanket `NETWORK_IDENTITY_UNCORRELATED` only where evidence supports it; unresolved cases keep current classification.
- **Dependencies:** Phase 1 tracer + normalizer extension points.
- **Tests:** Unit (DNS line parsing), integration (declared hostname ↔ observed IP correlated run), negative (no-DNS-evidence run stays uncorrelated), determinism via recorded logs.
- **Acceptance:** Reference run correlates `93.184.216.34` ↔ `api.example.com` only with DNS evidence present; without it, output identical to today.
- **Exit criteria:** Correlated and uncorrelated paths both covered by tests; no IP→hostname claim without evidence.
- **Risks:** Encrypted DNS / cached resolvers may yield no observable query; timeout behavior must stay deterministic.
- **Excluded:** Lockfiles, eBPF, baselines, drift, AI, cloud, dashboard.

## Phase 3 — Lockfile & Dependency Resolution (PLANNED)

- **Objective:** Attribute package artifacts as direct vs transitive using lockfiles.
- **Scope:** Parsers for `poetry.lock`, `package-lock.json`, `pnpm-lock.yaml`; resolution mapping consumed by reconciliation; artifact explanations upgraded only where resolution evidence exists.
- **Dependencies:** Static-analysis parser interface (unchanged).
- **Tests:** Lockfile fixture parsing, direct/transitive attribution, unresolved-artifact fallback identical to today.
- **Acceptance:** Reference artifacts attributed where lockfile proves it; others keep `observation_type=observed_package_artifact` wording.
- **Exit criteria:** No artifact ever labeled direct/transitive without lockfile evidence.
- **Risks:** Lockfile schema drift across ecosystems; scope to pinned, well-documented formats first.
- **Excluded:** DNS already done; eBPF, baselines, drift, AI, cloud, dashboard.

## Phase 4 — Behavioral Baselines (PLANNED)

- **Objective:** Accepted-behavior baseline model with explicit comparison semantics.
- **Scope:** Baseline schema (accepted findings/observations per project version), `baseline create` promotion from run-compare scaffolding to semantic baselines, comparison rules.
- **Dependencies:** Stable finding taxonomy (Phase 1 cleanup) + storage versioning.
- **Tests:** Baseline creation, comparison (new/resolved/persistent), schema migration.
- **Acceptance:** `diff` output distinguishes accepted vs novel behavior per baseline.
- **Exit criteria:** Baseline semantics documented; drift detection still excluded.
- **Risks:** Baseline staleness; require explicit re-baselining workflow, never silent acceptance.
- **Excluded:** Drift detection (Phase 5), eBPF, AI, cloud, dashboard.

## Phase 5 — Behavioral Drift (PLANNED)

- **Objective:** Detect drift across versions/runs against baselines.
- **Scope:** `BEHAVIORAL_DRIFT` finding emission rules, thresholds, evidence linkage.
- **Dependencies:** Phase 4 baselines.
- **Tests:** Drift positive/negative controls, threshold tests, determinism.
- **Acceptance:** Controlled behavior change yields drift finding with evidence; identical reruns yield none.
- **Exit criteria:** False-positive rate measured per Evaluation Plan before any CI gating.
- **Risks:** Noisy environments cause flapping; thresholds must be evidence-based.
- **Excluded:** eBPF, AI, cloud, dashboard.

## Phase 6 — Additional Runtime Observation Backends (PLANNED)

- **Objective:** eBPF (or equivalent) backend emitting the unchanged canonical contract.
- **Scope:** New `RuntimeObserver` + normalizer mapping to existing `RuntimeEventType`s; reconciliation untouched.
- **Dependencies:** TR-022 interfaces; kernel/toolchain availability.
- **Tests:** Backend parity tests (same fixture, equivalent canonical events), unavailability handling.
- **Acceptance:** Same demo yields equivalent observed models across backends within documented tolerance.
- **Exit criteria:** Reconciliation code unchanged (verified by diff).
- **Risks:** Privilege/kernel-version matrix; document minimum requirements.
- **Excluded:** AI, cloud, dashboard, Kubernetes.

## Phase 7 — Research Evaluation (PLANNED)

- **Objective:** Execute Evaluation Plan v1.0 measurement protocol and publish results.
- **Scope:** Controlled cases, metrics collection, overhead/reproducibility measurement.
- **Dependencies:** All prior phases as implemented.
- **Tests:** Evaluation harness reruns; results recorded, never invented.
- **Acceptance:** Metrics table completed with methodology notes; no unsupported performance claims.
- **Exit criteria:** Results reviewed before any release claim.
- **Risks:** Overgeneralization from demo fixture; expand fixture corpus first.
- **Excluded:** Productization (CI action, gating thresholds) until evaluation is reviewed.
