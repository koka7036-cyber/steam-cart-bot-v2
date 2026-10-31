# Windows local dispatcher — deployment plan

## Decision

Use the Windows PC as the durable execution host and keep dispatcher state in a local SQLite database. Do **not** register this personal PC as a GitHub repository runner.

The worker is a separate local process started by an explicit Windows Scheduled Task after the machine is prepared. GitHub Actions remains a hosted, read-only preflight. This avoids giving arbitrary pull-request workflows execution access to the user's PC.

## State location

Default production path:

```text
C:\CardBot\dispatcher-state\dispatcher.sqlite3
```

Requirements:
- The database and its directory must be on a local NTFS volume, not OneDrive, a network share, or a synchronized folder.
- One designated worker process owns the SQLite file. Do not start a second independent worker against the same database until multi-process WAL initialization and contention tests have passed on the target Windows/NTFS environment. `BEGIN IMMEDIATE` serializes write transactions but does not replace process-level startup coordination around WAL setup and schema migrations.
- Restrict directory ACLs to the dedicated Windows account that runs the worker and local administrators.
- Keep SQLite WAL/SHM files beside the database; do not copy only the main DB while the worker is running.
- Back up the database using SQLite's online backup API or after a clean worker shutdown.
- Never store GitHub tokens, Codex credentials, Steam sessions, marketplace tokens, order payloads, or voucher codes in the dispatcher database.

## Process model

1. A local Windows worker polls the GitHub Issues API using a read-only credential.
2. It applies the existing fail-closed policy: open issue, explicit `codex-ready`, no blocking labels, and explicit `Files to change:` allowlist.
3. It atomically claims one issue in the local SQLite database. The lease is valid only on this one PC/database.
4. It creates a disposable Git worktree on a dedicated branch from the approved base commit.
5. Codex runs only inside that worktree with workspace-write sandboxing, no network access, and a bounded time/iteration budget. It receives no GitHub write token and no marketplace/runtime secrets.
6. The worker rejects the result if any changed path is outside the issue allowlist or touches protected paths. It runs the repository's required tests.
7. Only a separate publisher step may use Git credentials to push a new branch and open a **Draft PR**. The Codex process itself never receives those credentials.
8. The worker records completion/failure in SQLite. A completed issue is not run again unless an operator explicitly resets it.

## Security boundary

- Do not use a GitHub `self-hosted` runner label on the personal PC for workflows triggered by pull requests. Untrusted PR code could execute on the PC with the runner account's local access.
- Do not expose a local SQLite file over the internet or through a public tunnel.
- Do not put GitHub write tokens in Codex's environment.
- Do not let Codex modify workflows, deployment scripts, Windows startup scripts, credentials, runtime state, inventory, orders, or FunPay/Playerok mutation code.
- Do not run sales, Steam POST requests, trade delivery, or marketplace writes from the dispatcher.
- The worker must stop on unknown configuration, missing tools, failed tests, expired lease, or an unexpected diff. Fail closed.
- Treat legacy lease rows with a NULL fencing token as non-renewable/non-finishable. Do not backfill tokens into active legacy rows: allow them to expire and reclaim them so an old process cannot be legitimized by migration.

## Windows prerequisites

Before enabling a scheduled task, an operator must verify on the target PC:
- Windows 11 and a local NTFS path at `C:\CardBot`.
- Python version compatible with the repository.
- Git is installed and the repository clone is clean.
- Codex CLI is installed and authenticated for the intended account.
- A dedicated least-privilege GitHub read credential is available to the worker.
- A separate publishing credential with only repository contents and pull-request permissions is available only to the publisher process.
- The machine's sleep/power policy is understood. The worker cannot operate while the PC is powered off or asleep.

## Rollout gates

### Gate 0 — preflight only
Verify tools, paths, ACLs, repository state, and SQLite read/write/locking on the PC. No Codex invocation, Git push, PR creation, or sales.

### Gate 1 — local claim and dry-run
Poll the queue, claim one test issue, write a sanitized task manifest, and release/finish the lease. Confirm restart recovery and duplicate-claim rejection.

### Gate 2 — isolated Codex run
Enable only after sandbox behavior, environment scrubbing, file allowlist enforcement, timeout, and process termination are tested. Keep network disabled and do not publish.

### Gate 3 — Draft PR handoff
Enable a separate publisher after branch isolation, patch validation, test reports, and credential separation pass. Draft PR only; never auto-merge.

### Gate 4 — bot acceptance
The dispatcher remains separate from the live sales bot. Sales activation requires its own manual acceptance checklist and explicit operator action.

## Current implementation status

The repository currently contains the SQLite lease primitives and a read-only hosted preflight. The local Windows worker, Codex process isolation, publisher, scheduled task, and PC-side validation are **not implemented or enabled**. This document is a deployment design, not evidence that the PC has been configured.
