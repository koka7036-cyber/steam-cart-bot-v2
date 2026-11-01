# FunPay refund-safe manual offer reconciliation

## Intent
Prevent the administrator-only `/fpofferresolve` command from overwriting a FunPay refund or refund-review state while reconciling a Steam trade offer.

## Goals
- Block both `accepted` and `returned` resolutions whenever `funpay_refunded` is true.
- Block both resolutions whenever the order status is `refund_review`, `refunded`, or `refunded_cancelled`.
- Keep existing manual reconciliation behavior unchanged for eligible orders with a Steam offer.
- Keep the check inside the existing `funpay_orders_lock` critical section.

## Non-goals
- Do not change FunPay refund registration, Steam offer creation, inventory cache freshness, or stock restoration semantics.
- Do not enable automatic FunPay delivery or auto-start.
- Do not resolve refund disputes automatically.

## Constraints
- Preserve the current JSON ledger schema; no migration.
- Keep the helper dependency-free in `funpay_orders.py`.
- Add regression tests before production changes.
- The main branch must remain untouched; deliver via a separate PR.
- A Steam offer being accepted/returned does not itself settle a FunPay refund dispute.

## Approaches
1. Add a small pure validation helper in `funpay_orders.py` and call it from `/fpofferresolve` while holding the existing lock. This centralizes the rule and is directly testable.
2. Add inline checks only in `bot.py`. This is a smaller textual change but leaves the rule untested without importing the large bot module.
3. Automatically reconcile refund-review orders based on Steam offer status. Rejected because it would collapse two independent payment/delivery systems and could hide an unresolved refund dispute.

## Chosen approach
Use option 1. It adds a focused pure function and unit tests without changing the ledger schema or network behavior.


## In-flight refund race

A FunPay refund may be processed while the Steam trade-offer POST is still running. When the Steam response is later persisted, the code must preserve `refund_review` (or an existing final refund status) instead of replacing it with `offer_sent`, `delivery_uncertain`, or `retry_required`. If Steam returns an offer ID, persist that ID and confirmation metadata while keeping the reservation and refund-review state. Keep the network request outside `funpay_orders_lock`; reconcile the response under the lock using the latest ledger record.
