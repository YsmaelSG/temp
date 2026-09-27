def test_list_accounts(client):
    res = client.get("/api/accounts")
    assert res.status_code == 200
    ids = [a["id"] for a in res.get_json()["data"]]
    assert ids == ["acc_1", "acc_2"]


def test_balance_is_computed_from_transactions(client):
    # acc_1: +1000.00 - 12.50 - 40.00
    res = client.get("/api/accounts/acc_1")
    assert res.get_json()["balance_cents"] == 100000 - 1250 - 4000


def test_get_unknown_account_is_404(client):
    res = client.get("/api/accounts/acc_999")
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "not_found"


def test_transactions_are_newest_first_and_paginated(client):
    res = client.get("/api/accounts/acc_1/transactions?limit=2")
    body = res.get_json()
    assert [t["id"] for t in body["data"]] == ["txn_3", "txn_2"]
    assert body["next_cursor"] is not None

    res = client.get(f"/api/accounts/acc_1/transactions?limit=2&cursor={body['next_cursor']}")
    body = res.get_json()
    assert [t["id"] for t in body["data"]] == ["txn_1"]
    assert body["next_cursor"] is None


def test_filter_by_type(client):
    res = client.get("/api/accounts/acc_1/transactions?type=credit")
    assert [t["type"] for t in res.get_json()["data"]] == ["credit"]


def test_create_transaction(client):
    res = client.post("/api/transactions", json={
        "account_id": "acc_1", "type": "debit", "amount_cents": 500, "description": "Coffee",
    })
    assert res.status_code == 201
    txn = res.get_json()
    assert res.headers["Location"] == f"/api/transactions/{txn['id']}"
    assert client.get("/api/accounts/acc_1").get_json()["balance_cents"] == 94750 - 500


def test_create_requires_fields(client):
    res = client.post("/api/transactions", json={"account_id": "acc_1", "type": "debit"})
    assert res.status_code == 422


def test_create_rejects_non_json_body(client):
    res = client.post("/api/transactions", data="not json")
    assert res.status_code == 400


def test_create_rejects_float_amount(client):
    res = client.post("/api/transactions", json={"account_id": "acc_1", "type": "credit", "amount_cents": 10.5})
    assert res.status_code == 422


def test_debit_cannot_overdraw(client):
    res = client.post("/api/transactions", json={"account_id": "acc_1", "type": "debit", "amount_cents": 10_000_000})
    assert res.status_code == 409


def test_idempotency_key_prevents_duplicates(client):
    payload = {"account_id": "acc_1", "type": "debit", "amount_cents": 100}
    headers = {"Idempotency-Key": "abc-123"}
    first = client.post("/api/transactions", json=payload, headers=headers)
    second = client.post("/api/transactions", json=payload, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.get_json()["id"] == second.get_json()["id"]
    assert client.get("/api/accounts/acc_1").get_json()["balance_cents"] == 94750 - 100
