"""Ledger: a tiny personal-finance app.

Run:  python backend/app.py   then open http://localhost:5000
"""
import base64
import os

from flask import Blueprint, Flask, jsonify, request, send_from_directory

from store import Store
from validators import APIError, parse_limit, validate_new_transaction

bp = Blueprint("api", __name__, url_prefix="/api")


def get_store() -> Store:
    from flask import current_app
    return current_app.config["STORE"]


# ---------- cursor helpers ----------
# The cursor is an opaque string to clients. Internally it's a position in
# the account's append-only transaction list.

def encode_cursor(pos: int) -> str:
    return base64.urlsafe_b64encode(str(pos).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        raise APIError(400, "invalid_cursor", "Malformed cursor")


# ---------- accounts ----------

@bp.get("/accounts")
def list_accounts():
    accounts = get_store().list_accounts()
    return jsonify({"data": [a.to_dict() for a in accounts]})


@bp.get("/accounts/<account_id>")
def get_account(account_id):
    account = get_store().get_account(account_id)
    if account is None:
        raise APIError(404, "not_found", f"Account {account_id} not found")
    return jsonify(account.to_dict())


@bp.get("/accounts/<account_id>/transactions")
def list_account_transactions(account_id):
    store = get_store()
    if store.get_account(account_id) is None:
        raise APIError(404, "not_found", f"Account {account_id} not found")

    limit = parse_limit(request.args.get("limit"))
    txn_type = request.args.get("type")
    if txn_type is not None and txn_type not in ("credit", "debit"):
        raise APIError(400, "invalid_type", "'type' must be 'credit' or 'debit'")
    cursor = request.args.get("cursor")
    before = decode_cursor(cursor) if cursor else None

    page, next_pos = store.list_account_transactions(account_id, limit, before, txn_type)
    return jsonify({
        "data": [t.to_dict() for t in page],
        "next_cursor": encode_cursor(next_pos) if next_pos is not None else None,
    })


# ---------- transactions ----------

@bp.get("/transactions/<txn_id>")
def get_transaction(txn_id):
    txn = get_store().get_transaction(txn_id)
    if txn is None:
        raise APIError(404, "not_found", f"Transaction {txn_id} not found")
    return jsonify(txn.to_dict())


@bp.post("/transactions")
def create_transaction():
    store = get_store()

    # A retried request with the same key gets the original response back
    # instead of creating a duplicate transaction.
    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        previous = store.get_idempotent_result(idem_key)
        if previous is not None:
            status, body = previous
            return jsonify(body), status

    data = validate_new_transaction(request.get_json(silent=True))
    account = store.get_account(data["account_id"])
    if account is None:
        raise APIError(404, "not_found", f"Account {data['account_id']} not found")
    if data["type"] == "debit" and data["amount_cents"] > account.balance_cents:
        raise APIError(409, "insufficient_funds", "Debit exceeds account balance")

    txn = store.create_transaction(
        account_id=data["account_id"],
        txn_type=data["type"],
        amount_cents=data["amount_cents"],
        description=data["description"],
    )
    body = txn.to_dict()
    if idem_key:
        store.save_idempotent_result(idem_key, 201, body)

    response = jsonify(body)
    response.status_code = 201
    response.headers["Location"] = f"/api/transactions/{txn.id}"
    return response


# ---------- app factory ----------

def create_app(data_dir: str | None = None) -> Flask:
    base = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, static_folder=os.path.join(base, "static"))
    app.config["STORE"] = Store(data_dir or os.path.join(base, "..", "data"))
    app.register_blueprint(bp)

    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return jsonify({"error": {"code": err.code, "message": err.message}}), err.status

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify({"error": {"code": "not_found", "message": "Route not found"}}), 404

    @app.errorhandler(405)
    def handle_405(_):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed"}}), 405

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
