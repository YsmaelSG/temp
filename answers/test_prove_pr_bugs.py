"""Tests that PROVE the PR's bugs. Each one passes on correct code and fails on the PR.

    git checkout pr/categories-summary
    python -m pytest answers/ -v        # watch these fail
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest import client  # noqa: E402,F401  (reuse the fixture)

from app import create_app  # noqa: E402


# Bug 1: the spec says only the category may change, but PATCH changes anything.
def test_patch_cannot_change_amount(client):
    res = client.patch("/api/transactions/txn_2", json={"amount_cents": 1})
    assert res.status_code == 422
    assert client.get("/api/transactions/txn_2").get_json()["amount_cents"] == 1250


# Bug 1b: this also silently corrupts the balance.
def test_balance_matches_transactions_after_patch(client):
    client.patch("/api/transactions/txn_3", json={"type": "credit"})
    txns = client.get("/api/accounts/acc_1/transactions").get_json()["data"]
    expected = sum(t["amount_cents"] if t["type"] == "credit" else -t["amount_cents"] for t in txns)
    assert client.get("/api/accounts/acc_1").get_json()["balance_cents"] == expected


# Bug 2: PATCH doesn't validate the category.
def test_patch_rejects_invalid_category(client):
    res = client.patch("/api/transactions/txn_2", json={"category": "pizza"})
    assert res.status_code == 422


# Bug 3: the summary counts credits (the paycheck) as spending.
def test_summary_counts_debits_only(client):
    body = client.get("/api/accounts/acc_1/summary?month=2026-08").get_json()
    assert body["total_spent_cents"] == 1250   # only the Chipotle debit, not the $1000 paycheck


# Bug 4: a missing or malformed month should be 400. Instead it returns 200
# (all-time totals, or zeros).
def test_summary_requires_month(client):
    assert client.get("/api/accounts/acc_1/summary").status_code == 400


def test_summary_rejects_malformed_month(client):
    assert client.get("/api/accounts/acc_1/summary?month=2026-8").status_code == 400


# Bug 5: an unknown account should be 404. Instead store.accounts[id] raises KeyError, which is a 500.
def test_summary_unknown_account_is_404(client):
    assert client.get("/api/accounts/acc_999/summary?month=2026-08").status_code == 404


# Bug 6: breaking change. `created_at` was renamed to `date`, which breaks
# existing clients, including this repo's own frontend.
def test_existing_response_shape_unchanged(client):
    txn = client.get("/api/transactions/txn_1").get_json()
    assert "created_at" in txn


# Bug 7: category changes must survive a restart. PATCH only mutates memory,
# and even POSTed categories aren't written, because TXN_FIELDS wasn't updated.
def test_category_survives_restart(client):
    from flask import current_app  # noqa: F401
    res = client.post("/api/transactions", json={
        "account_id": "acc_1", "type": "debit", "amount_cents": 800, "category": "dining",
    })
    txn_id = res.get_json()["id"]
    client.patch("/api/transactions/txn_2", json={"category": "groceries"})

    data_dir = client.application.config["DATA_DIR"]
    restarted = create_app(data_dir=data_dir).test_client()
    assert restarted.get(f"/api/transactions/{txn_id}").get_json()["category"] == "dining"
    assert restarted.get("/api/transactions/txn_2").get_json()["category"] == "groceries"
