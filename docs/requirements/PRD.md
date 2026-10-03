# Runtime Truth — Product Requirements Document v1.0

**Version:** 1.0
**Status:** Baseline
**Date:** 2026-10-03
**Scope:** Describes the currently implemented system (v0.1 foundation + Phase 1 containerized runtime observation + semantic/reporting cleanup, 47 tests passing). No planned-phase features are described as implemented.

---

## 1. Product name

**Runtime Truth** — Declared Software Model vs Observed Runtime Behavior.

## 2. Problem statement

Modern software projects declare what they need across disconnected artifacts: `requirements.txt`, `pyproject.toml`, `package.json`, `Dockerfile`, JSON/YAML configuration, and source-code imports. What actually executes at runtime routinely diverges from those declarations:

- Declared dependencies are never imported or loaded (bloat, e.g. `unused-package` in `cases/demo-app/requirements.txt`).
- Package files are loaded at runtime without appearing in any manifest (transitive or undocumented loads, e.g. `urllib3`, `werkzeug` via `site-packages` access).
- Applications open outbound network connections to numeric IPs that cannot be trivially mapped to declared hostnames.
- Child processes are spawned without any entrypoint declaration.
- Files are read that no manifest or volume declaration accounts for.

Developers currently discover these divergences by accident, if at all. Runtime Truth makes the comparison systematic, deterministic, and evidence-backed.

## 3. Target users

1. **Application developers** verifying that a service does what its manifests claim before merging or releasing.
2. **Maintainers auditing dependency hygiene** (unused declarations, undocumented runtime loads).
3. **CI operators** gating releases on reproducible declared-vs-observed checks using offline replay logs.

Non-users in v1.0: security-operations teams seeking a vulnerability scanner, platform teams seeking Kubernetes admission control, or anyone needing a hosted dashboard. Those are explicitly out of scope.

## 4. User scenarios

- **S1 — Pre-release hygiene check.** A developer runs `runtime-truth scan cases/demo-app --mode docker` and learns `unused-package` is declared but never loaded, while ten `site-packages` package artifacts were accessed without direct declaration. They remove or document the discrepancy.
- **S2 — Deterministic CI replay.** A CI job runs `runtime-truth scan <path> --mode offline_events --offline-log <trace>` against a checked-in `strace` log, producing identical findings on every run without Docker or root.
- **S3 — Regression comparison.** A developer records a run with `runtime-truth baseline create <run-id> --name v1.0` and later runs `runtime-truth diff <run-a> <run-b>` to list new, resolved, and persistent findings.
- **S4 — Report review.** A reviewer opens the standalone `report.html` for a run, expands the evidence items under a finding, and traces a network observation back to the exact `connect(...)` syscall line in `raw/strace.log`.

## 5. Core value proposition

One question, answered with evidence rather than assertion:

> **What does the software declare, and what does it actually do at runtime?**

Every answer the product gives is traceable: finding → observed entity → canonical event → raw runtime evidence.

## 6. Goals

- G1. Extract a **Declared Model** from manifests and source without executing project code.
- G2. Capture **raw runtime evidence** (`strace` output) and preserve it losslessly per run.
- G3. Normalize raw evidence into **canonical events** behind a backend-agnostic contract.
- G4. Synthesize an **Observed Model** with per-entity **evidence** references.
- G5. **Reconcile** the two models deterministically and emit typed, severity-graded results.
- G6. Separate **actionable findings** from **informational observations** and **unresolved correlations** so routine runtime facts do not inflate discrepancy counts.
- G7. Run fully **local-first**: SQLite + local filesystem artifacts, no cloud, no network service dependency.

## 7. Non-goals

- Not a vulnerability scanner and never labels findings as vulnerabilities or CVEs.
- No dependency resolution (direct vs transitive), no DNS interception, no eBPF, no behavioral baselines/drift detection, no AI/LLM reasoning, no Kubernetes, no cloud service, no web dashboard. These are either future phases (see TDP v1.0) or permanently out of scope (see §13).

## 8. Functional requirements (summary; normative IDs live in TRD v1.0)

- FR-1. Static analysis of Python AST imports (with stdlib tagging), `requirements.txt`, `pyproject.toml` (PEP 621 + Poetry), `package.json`, `Dockerfile` (`EXPOSE`, `ENV`, `CMD`/`ENTRYPOINT`, `WORKDIR`, `VOLUME`), and safe JSON/YAML config extraction (URLs, ports, environment mappings).
- FR-2. Runtime observation via Docker tracer image (`runtime-truth-tracer:latest`), host `strace`, or offline log replay — all through the `RuntimeObserver` contract.
- FR-3. `strace` normalization for `connect`, `openat`/`open`, `execve`, `unlink`/`unlinkat`, `exit_group`; failed `execve` path probes (`= -1 ENOENT`) are not process spawns.
- FR-4. Observed-model synthesis: package artifacts from `site-packages`/`dist-packages` access, network destinations, filesystem paths (system paths and expected workspace activity suppressed), processes (first spawn = target process).
- FR-5. Reconciliation with stdlib filtering, workspace-activity suppression, numeric-IP-vs-hostname handling (`NETWORK_IDENTITY_UNCORRELATED`), and target-process exclusion from findings.
- FR-6. Reporting in three channels (CLI tables, JSON, standalone HTML) with the three-way summary: Actionable Findings / Informational Observations / Unresolved Correlations.
- FR-7. Persistence: SQLite run database plus per-run artifact directory including `raw/strace.log`.

## 9. User workflows

**Scan (Docker):** `runtime-truth scan cases/demo-app --mode docker` → builds/locates tracer image → mounts target read-only → traces execution → normalizes → reconciles → prints three-section summary → writes `.runtimetruth/runs/<run-id>/` artifacts.

**Scan (offline):** `runtime-truth scan <path> --mode offline_events --offline-log <file>` → identical pipeline from a recorded log; fully deterministic.

**Scan (static only):** `runtime-truth scan <path>` → declared model, empty observed model, declaration-side findings only.

**Inspect:** `runtime-truth report <run-id> [--format cli|json|html]` reads stored results; never re-executes the target.

**Compare:** `runtime-truth baseline create <run-id> --name <n>` snapshots findings JSON; `runtime-truth diff <a> <b>` reports new/resolved/persistent findings.

## 10. Expected outputs

Per run, under `.runtimetruth/runs/<run-id>/`: `declared.json`, `raw/strace.log` (when runtime observation ran), `events.jsonl`, `observed.json`, `findings.json`, `report.html`. Terminal summary shows Declared/Observed entity counts plus the three-way finding summary. JSON reports carry the same summary plus full models and evidence. HTML reports render three cards and three sections (Actionable Findings, Unresolved Correlations, Informational Observations) with expandable evidence items.

Reference live result (`cases/demo-app`, `--mode docker`): 21 declared entities, 18 observed entities, Actionable 3 (`unused-package`, `api.example.com` declared-not-observed, `/usr/bin/echo` child process), Informational 10 (package artifacts), Unresolved 1 (`93.184.216.34` vs declared `api.example.com`).

## 11. Supported execution model

Linux-first, Docker-compatible. Host requirements: Python 3.12+, Docker daemon for `--mode docker`. The host never needs `strace` installed for Docker or offline modes. Container execution uses `--cap-add=SYS_PTRACE` (least privilege, no `--privileged`), read-only target mount (`:ro`), no Docker socket mount, no host credential exposure. See Threat Model v1.0 for boundaries and residual risks.

## 12. MVP scope

Exactly what the repository implements today: the pipeline in §8–§10, the `cases/demo-app` fixture (deterministic, non-malicious: config read, package imports, one `echo` child process, one short-timeout outbound socket attempt), 47 passing tests, and the documentation set itself.

## 13. Future scope

Phase 2 DNS resolution / network identity correlation; Phase 3 lockfile & dependency resolution; Phase 4 behavioral baselines; Phase 5 behavioral drift; Phase 6 additional observation backends (eBPF); Phase 7 research evaluation. Details and acceptance criteria in TDP v1.0. Permanently out of scope: AI reasoning, Kubernetes integration, cloud services, web dashboards.

## 14. Explicit limitations

- Observed numeric IPs are **not** correlated to declared hostnames until Phase 2; they are reported as `NETWORK_IDENTITY_UNCORRELATED`, never as proven undeclared.
- `site-packages` access yields **package artifacts**, never a proven direct-dependency claim.
- Standard-library imports never become third-party dependency findings.
- The first spawned process is the **target process** (kept in the observed model, not emitted as a finding); only subsequent child processes can be discrepancies.
- Files under the declared workspace matching project sources are expected activity, not discrepancies.
- The tracer container is an observation environment, **not** a proven security sandbox (see Threat Model v1.0).

## 15. Success criteria

- `pytest -v`: 47/47 passing.
- Live `runtime-truth scan cases/demo-app --mode docker` completes and reproduces the §10 reference counts within normal runtime variance of event volume.
- Every runtime-derived finding traces finding → observed entity → canonical event → `raw/strace.log` line (verified manually for the reference run).
- No `Total Discrepancies` metric remains in code or reports; the three-way summary is used consistently across CLI, JSON, and HTML.

---

## Terminology (frozen, consistent with TRD/TDP)

- **DECLARED** — explicitly represented by project metadata/configuration.
- **OBSERVED** — directly supported by runtime evidence.
- **PACKAGE ARTIFACT** — package-related runtime observation; not automatically a direct dependency.
- **TARGET PROCESS** — process intentionally executed as the workload (first spawn; in observed model only).
- **CHILD PROCESS** — process spawned by the workload (e.g. `/usr/bin/echo`).
- **UNRESOLVED CORRELATION** — observation not yet confidently mappable to a declared entity (numeric IP vs hostname).
- **FINDING** — reconciliation result requiring attention (actionable) or recorded interpretation.
- **EVIDENCE** — underlying observation supporting an assertion.
