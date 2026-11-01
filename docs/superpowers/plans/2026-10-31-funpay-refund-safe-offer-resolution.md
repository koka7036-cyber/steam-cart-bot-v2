# FunPay refund-safe offer resolution Implementation Plan

> **For agentic workers:** Use the inline execution workflow and complete each step in order. Steps use checkbox syntax for tracking.

**Goal:** Prevent manual Steam offer resolution from overwriting a recorded FunPay refund or refund-review state.

**Architecture:** Add a pure guard helper to `funpay_orders.py`; call it from the existing locked `/fpofferresolve` handler in `bot.py`. Cover refund flags, refund statuses, allowed statuses, and unchanged eligible outcomes with pytest.

**Tech Stack:** Python, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-31-funpay-refund-safe-offer-resolution-design.md`

## Global Constraints
- Preserve the current JSON ledger schema; no migration.
- Keep the helper dependency-free in `funpay_orders.py`.
- Add regression tests before production changes.
- The main branch must remain untouched; deliver via a separate PR.
- A Steam offer being accepted/returned does not itself settle a FunPay refund dispute.

## Review Focus
- A legacy record with `funpay_refunded=True` but a non-refund status must remain blocked.
- A record in `refund_review` with a missing/false refund flag must remain blocked.
- Both resolution actions must be blocked, not only `returned`.
- Eligible statuses must preserve existing behavior.
- The guard must run under the existing order lock to avoid a refund race.

---

### Task 1: Add refund-safe offer resolution guard

**Files:**
- Modify: `funpay_orders.py`
- Modify: `bot.py`
- Test: `tests/test_funpay_orders.py`

**Interfaces:**
- Produces: `offer_resolution_block_reason(record: dict, resolution: str) -> str | None`
- Consumes: the helper from the existing `bot.py` command handler.

- [x] **Step 1: Write failing tests first**
  - Add parametrized tests proving both `accepted` and `returned` are blocked for `funpay_refunded=True`.
  - Add parametrized tests proving both actions are blocked for `refund_review`, `refunded`, and `refunded_cancelled`.
  - Add tests proving eligible statuses `offer_sent`, `offer_pending_confirmation`, `delivery_uncertain`, and `sending` return `None` for both valid resolutions.
  - Add a test proving unsupported resolution is rejected.

- [x] **Step 2: Run the focused test and verify RED**
  - Run: `python -m pytest -q`
  - Expected: 17 new cases fail with ImportError because `offer_resolution_block_reason` does not exist yet; 156 existing tests pass.

- [x] **Step 3: Implement the pure guard**
  - In `funpay_orders.py`, return a non-empty Russian block reason for a non-dict record, unsupported resolution, a true refund flag, or a refund/refund-review status.
  - Return `None` only for `accepted` or `returned` when status is one of the four existing offer-resolution statuses and no refund marker exists.

- [x] **Step 4: Integrate the guard**
  - Import the helper in `bot.py`.
  - In `funpay_offer_resolve_cmd`, call it after loading the record and while still inside `funpay_orders_lock`; send its block reason and return before changing reservation, offer ID, or status.

- [x] **Step 5: Run verification**
  - Run: `pytest -q`
  - Expected: full suite passes — 173 passed.

- [x] **Step 6: Commit**
  - Commit the guard and integration with message `fix: block offer resolution after FunPay refunds`.



### Task 2: Preserve refund state across an in-flight Steam request

**Files:** `funpay_orders.py`, `bot.py`, `tests/test_funpay_orders.py`

**Interface:** `funpay_delivery_result_status(record: dict, outcome: str) -> str`

- [x] Add parametrized tests for all four Steam outcomes with refund-review, late refund flag, final refund statuses, and ordinary status mapping.
- [x] Verify RED on the test-only commit: 32 new cases failed to import the missing helper while 173 existing tests passed.
- [x] Add a pure helper that preserves refund-review and final refund states.
- [x] Apply the helper when persisting the Steam response under the existing order lock.
- [x] Add an administrator warning when the refund overlaps an in-flight delivery.
- [x] Run final CI on the latest commit: 205 passed; compileall, PowerShell syntax/updater integrity, and Playerok read-only SDK smoke passed. Review the complete PR diff.
