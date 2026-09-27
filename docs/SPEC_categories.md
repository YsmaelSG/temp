# Design Spec: Transaction Categories & Monthly Spending Summary

**Status:** Approved · **Owner:** Ledger team

## Background

Users can see their balance and transaction history, but they can't tell
*where* their money goes. We want to let users categorize transactions and
see a monthly breakdown of spending by category.

## Requirements

1. Every transaction has a `category`. Allowed values:
   `groceries`, `dining`, `transport`, `housing`, `entertainment`, `other`.
2. Transactions that already exist get the category `other`.
3. `POST /api/transactions` accepts an optional `category`, defaulting to
   `other`. An invalid category is rejected with `422`.
4. Users can re-categorize a transaction after it was created.
   - **Only the category may change.** Transactions are otherwise immutable:
     `amount_cents`, `type`, `account_id`, `description` and `created_at` must
     never change after creation. A request that tries to change any other
     field is rejected with `422`.
5. Category changes must survive a server restart.
6. Users can get a monthly spending summary for one account:
   - The response has the total **spending** per category for the given month.
   - Spending means **debits only**. Credits (paychecks, transfers in,
     refunds) must not be counted.
   - All six categories appear in the response, with `0` when there was no
     spending in that category.
   - `month` is required, in the format `YYYY-MM`. A missing or malformed
     month returns `400`. An unknown account returns `404`.

Example response:

```json
{
  "account_id": "acc_1",
  "month": "2026-09",
  "currency": "USD",
  "totals_cents": {
    "groceries": 8423, "dining": 3150, "transport": 0,
    "housing": 95000, "entertainment": 1299, "other": 0
  },
  "total_spent_cents": 107872
}
```

## Constraints

- **Do not change the shape of any existing API response**, other than adding
  the new `category` field. The mobile app parses these responses, and old
  app versions stay in use for months.
- **The summary must only look at the requested account's transactions.**
  Some accounts have tens of thousands of transactions, so scanning every
  account's transactions on each summary request is not acceptable.
- Errors must use the existing error format: `{"error": {"code", "message"}}`.

## Out of scope

- User-defined, custom categories.
- Auto-categorization. This may come in a future release.
- Frontend changes. These will ship in a separate PR.
