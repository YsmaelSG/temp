# Answer Key

Don't read a section until you've done that phase out loud.

---

## Phase 1: Explore

**UI → endpoints (Step A):**

| UI element | Endpoint |
|---|---|
| Account list (left) | `GET /api/accounts` |
| Account header + balance | `GET /api/accounts/{id}` |
| Transaction table | `GET /api/accounts/{id}/transactions?limit=10` |
| Filter dropdown | same, plus `&type=credit\|debit` (optional, so a query param) |
| "Load more" | same, plus `&cursor=<next_cursor from last response>` |
| "Add transaction" | `POST /api/transactions` with body `{account_id, type, amount_cents, description}` and an `Idempotency-Key` header |

The transactions list is nested under the account (`/accounts/{id}/transactions`)
because the account is required. Filters are query params because they're
optional.

**Trace of `GET /api/accounts/acc_1/transactions?limit=10&type=debit`:**
1. `app.py`: `create_app()` builds the `Store` and registers blueprint `bp` under `/api`.
2. `list_account_transactions` checks that the account exists (404 if not), then parses `limit` (400 if bad), `type` (400 if bad), and `cursor` (base64 → int).
3. `Store.list_account_transactions` walks `txn_ids_by_account["acc_1"]` **backwards** (newest first), skips non-matching types, and stops at `limit`.
4. The route serializes with `to_dict()` and returns `{"data": [...], "next_cursor": ...}` via `jsonify`.
5. The frontend (`index.html`) appends rows to the table, then stores `next_cursor` for "Load more."

**Data structures:**
- `accounts` and `transactions` are **dicts keyed by id**, so a lookup by id is O(1).
- `txn_ids_by_account` is a dict mapping each account id to a list of txn ids, a **secondary index**. Listing one account costs O(that account's txns), not O(all txns).
- `idempotency_results` is a dict mapping each key to `(status, body)`.

**Pagination:** it's cursor-based. The cursor is an opaque base64 string wrapping
a position in the account's id list. It stays stable because transactions are
**append-only**: new transactions go at the end, and pages read backwards from
a fixed position, so nothing shifts under the reader. That wouldn't hold if
deletes existed.

**Balance:** computed once at load (the sum of signed amounts), then kept as a
running total in `_index()` on each create. That makes reading it O(1).
Tradeoff: it's derived state, so anything that mutates a transaction without
updating it corrupts the balance (see PR bug 1).

**Idempotency:** `POST` checks `Idempotency-Key` → returns the stored `(status, body)` if the key was seen before.

**Things you could flag in `main` (Q8). Any of these is a good answer:**
- **Check-then-act race on idempotency.** The key check happens *outside* the lock, so two concurrent requests with the same key can both miss and both create. Fix: do the check and the save under the lock, or reserve the key first.
- **Overdraft check is racy too.** The balance check is in the route, outside the lock. Two concurrent debits can both pass the check and overdraw. Fix: move the check into `create_transaction` under the lock.
- **Idempotency keys aren't tied to the request.** The same key with a *different* body returns the old result silently; Stripe returns an error in that case. The keys also live only in memory, are lost on restart, and grow without bound. Fix: store a hash of the body with each key, and expire keys with a TTL.
- **No auth or ownership.** Anyone can read any account. In prod: an auth decorator, plus a check that the caller owns the account.
- `GET /api/accounts` isn't paginated. That's fine at this size, but mention it.

---

## Phase 2: Design (model answer for SPEC_categories)

**Clarifying questions worth asking:**
- Can a *credit* have a category? It's harmless, but the summary ignores credits.
- Month boundaries: is the month in UTC or the user's timezone? Assume UTC, since `created_at` is UTC.
- Should the summary include months with no data (all zeros)? The spec implies yes.
- Does re-categorizing need history or audit? Assume last write wins.
- Is the frontend out of scope? Yes, per the spec.

**Data model:**
- Add `category: str = "other"` to `Transaction`, plus a `CATEGORIES` tuple of allowed values in `models.py`.
- Existing rows have no column, so the loader defaults them to `"other"`. Better still, run a **one-time migration** that rewrites the CSV with the new column. Write it atomically: write a temp file, then `os.replace`.
- Add `category` to `TXN_FIELDS` so new rows persist it.

**Persisting a category change (the hard part).** The transactions CSV is
append-only, so you can't just append a row. Options:
1. Rewrite the whole CSV on every PATCH (temp file plus rename). Simple, but O(n) per write, and it breaks the append-only model.
2. **An append-only `category_changes.csv`** with rows `(txn_id, category, changed_at)`, replayed on load so the last write wins. Each write is O(1), it keeps the append-only model, and you get an audit trail for free. ← Pick this one and say why.

**Endpoints:**

| Endpoint | Success | Errors |
|---|---|---|
| `POST /api/transactions` + optional `category` | 201 | 422 invalid category |
| `PATCH /api/transactions/{id}` body `{"category": "dining"}` | 200 + full txn | 400 not JSON, 422 any field other than category, 422 bad category, 404 unknown txn |
| `GET /api/accounts/{id}/summary?month=YYYY-MM` | 200 | 400 missing or malformed month, 404 unknown account |

- **PATCH over PUT**, because it's a partial update. It's **idempotent** here since it *sets* a value, so a retry is harmless and doesn't need an idempotency key.
- Model the summary as a sub-resource of the account and make it a GET, because it's read-only, safe, and cacheable.

**Summary algorithm:** use `txn_ids_by_account[account_id]` (the spec forbids
scanning all accounts) and make **one pass**: for each debit in the month, add
it to `totals[category]`. Start from `{c: 0 for c in CATEGORIES}` so every
category appears. That's O(k) for an account with k transactions.
- *Going further:* ids are in time order, so you could binary-search (`bisect`) to the start of the month and stop at the end, which is O(log k + m).
- Or keep precomputed totals keyed by `(account, month, category)`, updated on write and on re-categorize. Reads become O(1), but more state can drift. Offer this, but pick the simple option for now.

**Fit the codebase:** raise `APIError` so the existing handler formats errors,
put validation in `validators.py`, keep store logic in `Store` and not in the
route, and take the lock on writes.

**Tests:** default category on old rows, invalid category → 422, PATCH of
amount → 422, PATCH unknown → 404, summary excludes credits, summary with a bad
or missing month → 400, unknown account → 404, and a category that **survives a
restart** (build a second app on the same data dir).

---

## Phase 3: PR review findings

Ranked by severity. Each finding gives the problem, why it matters, how to prove it, and the fix.

### Blocking

**1. PATCH allows changing ANY field. This is a spec violation and corrupts data.** (`store.update_transaction`, `setattr` loop)
- The spec says *only the category may change*, and other fields must return 422.
- As written, `{"amount_cents": 1}` or `{"type": "credit"}` succeeds.
- Worse, `balance_cents` is a running total that isn't recomputed, so the balance silently drifts from the transactions. `setattr` also accepts arbitrary keys (`{"foo": 1}`).
- *Verify:* `curl -X PATCH localhost:5000/api/transactions/txn_0005 -H 'Content-Type: application/json' -d '{"amount_cents":1}'` returns 200. Then the balance no longer matches the sum of the transactions.
- *Fix:* reject any key other than `category` with 422, and only ever set `txn.category`.

**2. The summary counts credits as spending. This is a spec violation.** (`spending_summary`)
- The spec says *debits only*. The loop never checks `txn.type`, so paychecks inflate "spending."
- **The PR's own test asserts the wrong number:** `total_spent_cents == 101250` includes the $1,000 paycheck. The correct value is 1250. A passing test that encodes a bug is worth calling out explicitly.
- *Fix:* `if txn.type == "debit"`, and correct the test.

**3. Breaking API change: `created_at` was renamed to `date`. This is a spec violation.** (`Transaction.to_dict`)
- The spec says *don't change existing response shapes*. Old mobile clients will break.
- **This repo's own frontend breaks:** `t.created_at.slice(...)` throws, so the transaction table fails to render. *Verify:* check out the branch, run the app, click an account.
- *Fix:* revert the rename. If a new name is truly wanted, *add* `date` alongside `created_at` and deprecate the old field later.

**4. Scans every transaction in the system, 6 times. This is an efficiency problem and a spec violation.**
- The loop is `for category in CATEGORIES: for txn in store.list_all_transactions()`.
- That's O(6 × N) where N is *all transactions across all accounts*, and `list_all_transactions()` also copies the whole dict into a new list on every outer iteration.
- The spec explicitly forbids scanning every account's transactions.
- *Fix:* iterate `txn_ids_by_account[account_id]` once, accumulating into a dict keyed by category. That's O(k).

**5. Category changes aren't persisted. This is a completeness gap.**
- PATCH only mutates memory, so a restart loses it. The spec says changes must survive a restart.
- Also, `TXN_FIELDS` wasn't updated, so even the category set on **POST** isn't written to the CSV (`extrasaction="ignore"` silently drops it).
- *Verify:* POST with `category: dining`, restart the server, GET the transaction. It comes back as `other`.
- *Fix:* add `category` to `TXN_FIELDS` with a migration for the existing file, and persist changes, for example via an append-only `category_changes.csv`.

**6. Missing validation on the summary. This is a completeness and correctness problem.**
- A missing `month` gives `startswith("")`, which matches everything and silently returns **all-time** totals with a 200. The spec requires a 400.
- A malformed month (`2026-8`) returns 200 with zeros instead of 400.
- An unknown account hits `store.accounts[account_id]`, raises `KeyError`, and returns a **500 with an HTML error page**. The spec requires a 404, and every other route uses `get_account()` and raises `APIError`.

**7. PATCH doesn't validate the category.** `{"category": "pizza"}` is accepted.
The PR validates on POST but not on PATCH, which is an inconsistency.

### Should fix (not the biggest risks)

- **PATCH with a non-JSON body:** `request.get_json()` (not `silent=True`) raises a 415 with an HTML body, which is inconsistent with the JSON error format. With a JSON array body, `.items()` raises an AttributeError, which becomes a 500. Use `get_json(silent=True)` plus an `isinstance(dict)` check, as `POST` does.
- **Writes without the lock.** `update_transaction` mutates shared state without `self._lock`, unlike `create_transaction`.
- **Tests only cover the happy path.** There are no tests for: PATCH of an immutable field, bad category on PATCH, missing or bad month, unknown account, credits being excluded, or persistence across a restart. The tests "pass" because they only exercise what the author expected to work.
- **The PR description doesn't flag the breaking rename** as a breaking change.

### Nits

- A leftover `print(...)` debug statement in `spending_summary`. Use logging or remove it.
- `import json` is unused.
- The summary logic lives in the route. The codebase convention is for store logic to go in `Store` (e.g. `list_account_transactions`).

### How to phrase it

> "Before the code, I re-read the spec's constraints. Two are explicit: only
> category can change, and the summary must only look at the requested
> account. The PR violates both. PATCH does a setattr on any field, so I can
> change amount_cents. I verified that with a curl, and it also desyncs the
> balance, because balance is a running total. I'd block on that. Second..."

Always cover *what* the problem is, *where* it is, *the impact*, *the fix*, and *whether it blocks*.

---

## Bonus: SPEC_transfers model answer (key points)

- **Resource:** `POST /api/transfers` with body `{from_account_id, to_account_id, amount_cents}` and a **required** `Idempotency-Key` (retries must never move money twice). Returns 201 with the transfer and its two transaction ids.
- **Data model:** a new `transfers.csv` with `(id, from_account_id, to_account_id, amount_cents, created_at)`. Add an optional `transfer_id` to `Transaction`. That's an additive change, so old clients are unaffected, and it satisfies "tell from a transaction whether it was part of a transfer."
- **Atomicity:** under one lock: validate, check the balance, create the debit and the credit and the transfer record, then persist. With CSVs you can't get a true multi-file transaction. Say so, and mention a write-ahead approach (write the transfer record first, then reconcile any half-applied transfer on load), or "in prod, a DB transaction."
- **Errors:** 404 unknown account, 409 insufficient funds, 422 same account / currency mismatch / bad amount.
- **Reads:** `GET /api/transfers/{id}`, and `GET /api/accounts/{id}/transfers` (paginated) or `GET /api/transfers?account_id=` (the filter is optional, so a query param works here).
- **No DELETE.** Reverse a transfer with a new transfer in the opposite direction.
- **Ownership:** both accounts must belong to the caller.
- **Tests:** the happy path, balances on both sides, insufficient funds, same account, a retry with the same key producing only one transfer, and a mismatched currency.

---

## Files in `answers/`

- `test_prove_pr_bugs.py`: 9 tests that fail on the PR and pass on a correct implementation. Run `git checkout pr/categories-summary && python -m pytest answers/ -v`.
- `fixes_to_pr.diff`: what the PR *should* have changed.
- `reference_solution.diff`: the full correct implementation against `main`.
