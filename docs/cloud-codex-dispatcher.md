# Cloud Codex task dispatcher — MVP

## Current behavior

The MVP provides a fail-closed task policy, a bounded read-only GitHub Issues
adapter, a JSON queue inspection CLI, and a manual preflight workflow. It does
not invoke Codex, claim issues, update labels, dispatch workflows, apply patches,
create branches, open pull requests, or change repository state.

The existing `.github/workflows/cloud-codex.yml` remains unchanged and is still
the only workflow that invokes Codex through AnyModel.

## Queue policy

An issue is eligible only when it is open, has the explicit `codex-ready` label,
has no `blocked`, `needs-human`, or `do-not-automate` label, has a bounded and
actionable description, and contains a non-empty Markdown file allowlist:

```text
Files to change:
- tests/test_order_parser.py
```

Only list entries immediately following this heading are treated as target
paths. Prose references and examples elsewhere in the issue body are not paths.
Absolute paths, parent traversal, `.git`, `.github`, and protected runtime,
sales, inventory, credential, deployment, and startup paths are rejected.

At most one issue is selected. Ordering is deterministic: priority label first,
then the lowest issue number. The adapter reads at most 10 pages of 100 results;
the CLI defaults to 2 pages. Pull requests are excluded from the Issues API
response. No issue state is modified.

## Protected scope

The policy rejects target files involving GitHub workflows/permissions and
secrets; runtime data, inventory, order ledgers, credentials, and Steam sessions;
Steam POST, FunPay/Playerok mutations, sales and automatic delivery; deployment,
Windows startup, and auto-start configuration.

## Read-only queue inspection

Run locally or in a read-only workflow:

```powershell
python -m dispatcher.queue_cli --repository owner/repo --max-pages 2 --per-page 100
```

For Actions, declare only `contents: read` and `issues: read`. No write
permissions are required for queue inspection.

As of 2026-10-31, the repository has no open Issues carrying `codex-ready`.
The preflight is expected to return `no_eligible_task` until a bounded issue
with the required explicit allowlist and label is added.

## Next phases

1. Add durable idempotency and a single-flight lease.
2. Add a dispatcher on the default branch that can trigger one bounded Codex
   run only after explicit approval.
3. Store patches as short-lived artifacts; never execute artifact files.
4. Validate patch size, file types, and paths in a low-privilege job.
5. Apply only approved patch files on an isolated branch, run CI, and open Draft
   PRs only. Never auto-merge.

Stop on duplicates, concurrency conflicts, protected paths, unclear scope,
test failures, timeout, budget exhaustion, missing permissions, or requests
involving real sales, marketplace mutations, runtime data, or startup changes.
