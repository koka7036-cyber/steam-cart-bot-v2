# Local archive synchronization audit — 2026-10-29

## Source of truth and validation

The user-provided Windows project archive was inspected as the current local snapshot. Its Python test suite passes in this environment: **89 passed**.

This is an audit note, not a claim that the entire local source tree has already been synchronized to GitHub. The archive's runtime state and credentials are intentionally excluded from source control.

## Confirmed differences

- Local `bot.py`: 145,752 bytes; GitHub PR branch `fix/funpay-reservation-restore-validation`: 114,875 bytes.
- Local `funpay_orders.py`: 24,071 bytes; GitHub PR branch: 21,003 bytes.
- Local `tests/test_funpay_orders.py`: 17,870 bytes; GitHub PR branch: 16,334 bytes.
- The local archive includes additional regression tests and newer FunPay chat parsing / order handling code.
- The local archive has two GitHub Actions workflow files. Their trigger and job definitions differ; they should be reviewed together before removing either, to avoid losing Windows PowerShell parsing and Playerok SDK smoke checks.

## Safety rules for synchronization

Do not commit these runtime files from the archive: `funpay_config.json`, `steam_session.json`, `funpay_orders.json`, `funpay_pending_inputs.json`, `inventory_cache.json`, `vouchers.json`, `bot_errors.log`, or `.asf_path.txt`. They can contain credentials, session data, buyer/order details, and live inventory state.

No live Steam offers, FunPay orders, or local Windows bot process were modified during this audit.

## Next synchronization scope

Port and review the local source changes in `bot.py`, `funpay_orders.py`, supporting modules, tests, and deployment scripts as source changes—not runtime JSON state. Run Python regression tests, compile checks, Windows PowerShell syntax checks, and the optional Playerok SDK smoke test before considering the sync ready.
