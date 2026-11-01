# Cloud Codex dispatcher — current implementation

The dispatcher currently supports a fail-closed read-only GitHub Issues queue,
explicit target-file allowlists, deterministic selection of at most one issue,
and a manual read-only preflight. It does not invoke Codex or mutate GitHub.

## Idempotency primitives

`dispatcher/idempotency.py` adds a SQLite lease backend for local processes
sharing the same durable database file:
- Task key is `owner/repo#issue_number`.
- `BEGIN IMMEDIATE` and a primary key serialize claims in one shared SQLite DB.
- Running, completed, and failed task states are distinct.
- A live lease cannot be claimed by another owner.
- A completed task cannot be claimed again.
- Failed tasks and expired leases can be reclaimed.
- Only the lease owner can renew or finish a running task.
- Workflow run IDs are recorded once.

**Important deployment boundary:** GitHub-hosted runners have separate temporary
filesystems. A SQLite database created under the runner workspace or temp path
is not durable across workflow runs and is not a cross-run lock. The workflow
does not create/use this store. Do not claim cross-run idempotency until the
database is backed by a persistent shared volume with SQLite locking guarantees,
or replaced by an atomic hosted store (for example, a transactional database or
conditional-write object store). GitHub Actions `concurrency` only prevents
overlapping runs in its group; it does not remember completed issue claims.

## Safety and workflow permissions

- The preflight workflow remains manual and dry-run only.
- It declares only `contents: read` and `issues: read`.
- No issue labels/comments are written and no workflow is dispatched.
- Codex still has no GitHub write token.
- No sales, marketplace mutations, runtime/order/inventory changes, secrets,
  deployment or Windows auto-start changes are allowed.
- No automatic merge.

## Tests

Run locally:

```powershell
python -m unittest discover -s dispatcher/tests -v
python -m compileall -q dispatcher
```

SQLite concurrency tests demonstrate single-flight only for processes sharing
one database file on a filesystem supporting SQLite locking. They do not
simulate independent GitHub-hosted runners.
