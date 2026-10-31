# Cloud Codex task guardrails

The manual workflow `.github/workflows/cloud-codex.yml` runs one bounded Codex CLI task through AnyModel.

## Safety model
- Trigger is manual only and restricted to the main ref.
- Codex receives workspace-write sandbox access in an ephemeral GitHub-hosted runner.
- The AnyModel API key is supplied only to the Codex invocation as `CODEX_API_KEY`.
- The agent receives no GitHub write token and cannot push, commit, or open PRs.
- The output is a short-lived patch artifact for human review; it is not applied automatically.
- Never use this workflow for real sales, Steam offers, FunPay writes, Playerok mutations, runtime data, secrets, inventory, order ledgers, deployment, or startup behavior.
- Keep tasks small, specific, and limited to ordinary source/tests/docs outside protected paths.
- Review the patch before applying it in a separate branch and running the full CI suite.

## Required repository secret
Add `ANYMODEL_API_KEY` in GitHub Settings → Secrets and variables → Actions. Never put the key in this repository, workflow inputs, logs, or chat.

## First-run requirements
1. Confirm the exact model ID in the AnyModel catalog.
2. Add the repository secret manually.
3. Run the workflow manually with a harmless read-only task first.
4. Confirm the API request works and inspect the artifact. Do not start with a code-edit task.
