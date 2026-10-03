# Runtime Truth — Threat Model v1.0

**Version:** 1.0
**Status:** Baseline
**Date:** 2026-10-03

## System sketch

```
                 HOST
                   │
          ┌────────┴────────┐
          │                 │
   Runtime Truth       Target Application
   (orchestrator,       (untrusted code,
    static analysis,     vendored deps)
    reporting, DB)            │
          │                 │
          └──── Docker ─────┘
        (tracer container:
         strace + target,
         --cap-add=SYS_PTRACE,
         read-only mount)
```

## Assets

- A1. Host filesystem, credentials (`~/.ssh`, `~/.config`, env), Docker daemon access.
- A2. Runtime Truth database and artifacts (runs, findings, `raw/strace.log`) — integrity of evidence.
- A3. Developer trust in findings (correctness of reconciliation output).
- A4. Host availability (CPU/memory, daemon responsiveness).

## Trust boundaries

- B1. **Static analysis ↔ target code:** parsers read but never execute project code (AST walk, TOML/JSON/YAML loads only). Crossed safely by construction.
- B2. **Host ↔ tracer container:** crossed via `docker run --rm --cap-add=SYS_PTRACE -v <target>:/app:ro -w /app`. Only the target directory is shared, read-only.
- B3. **Raw evidence → canonical events → findings:** crossed via normalizer/builder with per-event `raw_reference` linkage; tampering here breaks A2/A3.

## Threats, mitigations, residual risks

| # | Threat actor / action | Mitigation (implemented) | Residual risk |
|---|---|---|---|
| T1 | Malicious target writes to host via mount | Target mounted `:ro`; no `rw` scratch volume exists | Mount misconfiguration in future edits could re-open writes; review `build_docker_command` on every change |
| T2 | Malicious target escapes container | No `--privileged`, no Docker socket mount, no host creds mounted; base image minimal (`python:3.12-slim` + strace) | **NOT a proven sandbox.** Kernel/container-escape flaws are out of our control; never claim complete isolation |
| T3 | `SYS_PTRACE` abuse (ptrace scope) | Capability is container-scoped and required for `strace -f`; no host processes are traceable from inside the container's PID namespace | Capability widens in-container process introspection; a malicious target could ptrace sibling processes *inside the same container* |
| T4 | Compromised dependency exfiltrates data at runtime | Outbound `connect` is observed and reported (`NETWORK_*` findings) with raw evidence | Detection only — the connection attempt itself is not blocked; short-timeout demo attempt shows observation, not prevention |
| T5 | Malicious child process (`echo` pattern generalized) | All non-target spawns are `PROCESS_OBSERVED_NOT_DECLARED` with evidence | Process allow-listing does not exist; analyst must interpret |
| T6 | Resource exhaustion (fork bomb, trace flood) | `timeout_seconds` (default 30) bounds runs; `RunStatus.FAILED` on timeout | No CPU/memory cgroup limits are set on the tracer container today |
| T7 | Observer/evidence tampering (target pollutes strace via output) | Raw trace preserved verbatim; normalizer drops `<unfinished>`/`resumed>` fragments; event IDs bind run+line+sequence | A target aware of tracing can alter *its own* syscall pattern (trace-aware evasion); findings are evidence of observed behavior, not proof of total behavior |
| T8 | Network abuse from tracer (scanning, spam) | Demo uses single short-timeout connection; no `-p` published ports; default bridge egress only | Egress is **not** firewalled; arbitrary targets could attempt arbitrary outbound connections during a scan |
| T9 | Accidental credential exposure (env, files) in artifacts | No credential collection by design; artifacts contain only declared/observed values + raw trace | If a target prints secrets to stdout/stderr or reads secret files, trace/file paths land in artifacts — handle run directories as sensitive |
| T10 | Database/artifact integrity loss | SQLite + atomic artifact writes per run; conflict-safe upserts | No signing or append-only log; local attacker with filesystem access can alter history |

## Assumptions (explicit)

1. The operator runs only the repository's controlled demo fixture or otherwise-reviewed targets during tests — never arbitrary untrusted applications in test runs.
2. The Docker daemon and host kernel are trusted; container-escape vulnerabilities are out of scope for v1.
3. Findings are structural discrepancies with evidence, **never** vulnerability verdicts.
4. `SYS_PTRACE` + read-only mount + no socket/privilege is a *least-privilege observation setup*, not a formal security boundary.

## Out of scope for this model

Denial-of-service against public infrastructure, supply-chain compromise of the base image registry, and formal verification of isolation — none are addressed in v1.
