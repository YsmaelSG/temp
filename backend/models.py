from dataclasses import dataclass, asdict

TXN_TYPES = ("credit", "debit")


@dataclass
class Account:
    id: str
    owner_name: str
    name: str
    currency: str
    created_at: str
    balance_cents: int = 0  # derived at load time, maintained on every write

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Transaction:
    id: str
    account_id: str
    type: str          # "credit" (money in) or "debit" (money out)
    amount_cents: int  # always positive; direction comes from `type`
    description: str
    created_at: str    # ISO-8601 UTC, e.g. 2026-09-01T14:03:00Z

    def signed_amount(self) -> int:
        return self.amount_cents if self.type == "credit" else -self.amount_cents

    def to_dict(self) -> dict:
        return asdict(self)
