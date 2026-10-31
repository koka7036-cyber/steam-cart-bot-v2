# Cloud Codex task dispatcher — MVP

## Current behavior

This MVP adds a fail-closed task eligibility policy and a manual GitHub Actions
preflight. It is intentionally **read-only**: it does not call the GitHub API,
dispatch Cloud Codex, apply patches, create branches, or open pull requests.

The existing `.github/workflows/cloud-codex.yml` remains unchanged and continues
to be the only workflow that invokes Codex through AnyModel.

## Queue policy

An issue is eligible only when all conditions hold:

- State is `open`.
- It carries the explicit `codex-ready` label.
- It has no `blocked`, `needs-human`, or `do-not-automate` label.
- Title and body are bounded and the task is clearly actionable.
- The description does not request protected operations or data.
- Explicit paths mentioned in the task do not point into protected areas.

At most one issue is selected. Ordering is deterministic: priority label first,
then the lowest issue number. No automatic claim or state mutation is made.

## Protected scope

The first iteration rejects work involving:

- GitHub workflow files and CI/workflow permissions.
- Runtime data, inventory, order ledgers, credentials, and secrets.
- Steam POST, FunPay/Playerok mutations, sales, and automatic delivery.
- Deployment scripts, Windows startup scripts, and auto-start configuration.

The policy is deliberately conservative. False negatives are preferable to
passing a risky task to an automated coding agent.

## Run preflight

1. Open Actions → **Cloud Codex dispatcher preflight**.
2. Run on `main` with `dry_run=true`.
3. Inspect the workflow summary and tests.

The `dry_run=false` option is deliberately rejected until the next phase has
a reviewed implementation.

## Next phases

1. Add a read-only GitHub Issues adapter and verify label filtering/pagination.
2. Add durable idempotency and a single-flight lease before any Codex invocation.
3. Connect to the existing Codex workflow through a constrained handoff.
4. Retrieve and inspect artifacts, apply allowlisted patches on isolated branches,
   run CI, and create Draft PRs only.
5. Stop on any unsafe path, ambiguous patch, test failure, budget limit, or API
   error.

No phase may auto-merge, enable sales, send real marketplace operations, or
activate Windows auto-start.
