from models import TXN_TYPES

MAX_AMOUNT_CENTS = 1_000_000_00  # $1,000,000
MAX_DESCRIPTION_LEN = 140


class APIError(Exception):
    """Raised anywhere in a request; turned into a JSON error by app.py."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def validate_new_transaction(body) -> dict:
    if not isinstance(body, dict):
        raise APIError(400, "invalid_body", "Request body must be a JSON object")

    for field in ("account_id", "type", "amount_cents"):
        if field not in body:
            raise APIError(422, "missing_field", f"'{field}' is required")

    if body["type"] not in TXN_TYPES:
        raise APIError(422, "invalid_type", f"'type' must be one of {list(TXN_TYPES)}")

    amount = body["amount_cents"]
    # bool is a subclass of int in Python, so exclude it explicitly
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise APIError(422, "invalid_amount", "'amount_cents' must be an integer")
    if amount <= 0 or amount > MAX_AMOUNT_CENTS:
        raise APIError(422, "invalid_amount", "'amount_cents' must be between 1 and 100000000")

    description = body.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_LEN:
        raise APIError(422, "invalid_description", f"'description' must be a string of at most {MAX_DESCRIPTION_LEN} chars")

    return {
        "account_id": body["account_id"],
        "type": body["type"],
        "amount_cents": amount,
        "description": description.strip(),
    }


def parse_limit(raw, default: int = 20, maximum: int = 100) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise APIError(400, "invalid_limit", "'limit' must be an integer")
    if value < 1 or value > maximum:
        raise APIError(400, "invalid_limit", f"'limit' must be between 1 and {maximum}")
    return value
