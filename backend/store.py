"""In-memory data store backed by CSV files.

Everything is loaded into memory at startup. Writes update memory and
append to the CSV so data survives a restart. Transactions are
append-only: they are never edited or deleted.
"""
import csv
import os
import threading
import uuid
from datetime import datetime, timezone

from models import Account, Transaction

ACCOUNT_FIELDS = ["id", "owner_name", "name", "currency", "created_at"]
TXN_FIELDS = ["id", "account_id", "type", "amount_cents", "description", "created_at"]


class Store:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._lock = threading.Lock()

        self.accounts: dict[str, Account] = {}
        self.transactions: dict[str, Transaction] = {}
        # account_id -> list of txn ids, oldest first. Lets us list an
        # account's transactions without scanning every transaction.
        self.txn_ids_by_account: dict[str, list[str]] = {}
        # Idempotency-Key -> (status_code, response_body)
        self.idempotency_results: dict[str, tuple[int, dict]] = {}

        self._load()

    # ---------- loading ----------

    def _path(self, name: str) -> str:
        return os.path.join(self.data_dir, name)

    def _load(self) -> None:
        with open(self._path("accounts.csv"), newline="") as f:
            for row in csv.DictReader(f):
                acct = Account(
                    id=row["id"],
                    owner_name=row["owner_name"],
                    name=row["name"],
                    currency=row["currency"],
                    created_at=row["created_at"],
                )
                self.accounts[acct.id] = acct
                self.txn_ids_by_account[acct.id] = []

        with open(self._path("transactions.csv"), newline="") as f:
            rows = list(csv.DictReader(f))
        rows.sort(key=lambda r: r["created_at"])
        for row in rows:
            txn = Transaction(
                id=row["id"],
                account_id=row["account_id"],
                type=row["type"],
                amount_cents=int(row["amount_cents"]),  # CSV gives strings
                description=row["description"],
                created_at=row["created_at"],
            )
            self._index(txn)

    def _index(self, txn: Transaction) -> None:
        self.transactions[txn.id] = txn
        self.txn_ids_by_account[txn.account_id].append(txn.id)
        self.accounts[txn.account_id].balance_cents += txn.signed_amount()

    # ---------- reads ----------

    def list_accounts(self) -> list[Account]:
        return list(self.accounts.values())

    def get_account(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    def get_transaction(self, txn_id: str) -> Transaction | None:
        return self.transactions.get(txn_id)

    def list_account_transactions(
        self, account_id: str, limit: int, before: int | None, txn_type: str | None
    ) -> tuple[list[Transaction], int | None]:
        """Newest-first page of an account's transactions.

        `before` is a position in the account's (append-only) id list;
        the page starts just before it. Returns (page, next_position),
        where next_position is None when there are no more results.
        """
        ids = self.txn_ids_by_account[account_id]
        pos = len(ids) if before is None else before
        page: list[Transaction] = []
        while pos > 0 and len(page) < limit:
            pos -= 1
            txn = self.transactions[ids[pos]]
            if txn_type is None or txn.type == txn_type:
                page.append(txn)
        return page, (pos if pos > 0 else None)

    # ---------- writes ----------

    def create_transaction(
        self, account_id: str, txn_type: str, amount_cents: int, description: str
    ) -> Transaction:
        with self._lock:
            txn = Transaction(
                id="txn_" + uuid.uuid4().hex[:12],
                account_id=account_id,
                type=txn_type,
                amount_cents=amount_cents,
                description=description,
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            self._index(txn)
            with open(self._path("transactions.csv"), "a", newline="") as f:
                csv.DictWriter(f, fieldnames=TXN_FIELDS, extrasaction="ignore").writerow(
                    txn.to_dict()
                )
            return txn

    def get_idempotent_result(self, key: str) -> tuple[int, dict] | None:
        return self.idempotency_results.get(key)

    def save_idempotent_result(self, key: str, status: int, body: dict) -> None:
        self.idempotency_results[key] = (status, body)
