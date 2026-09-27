# Ledger

A small personal-finance web app. Users have accounts; accounts have
transactions (credits and debits). Data lives in CSV files and is loaded
into memory at startup.

## Run it

```bash
pip install -r requirements.txt
python backend/app.py          # then open http://localhost:5000
python -m pytest -q            # run the tests
```

## Layout

```
backend/      Flask app (API + serves the frontend)
data/         CSV data files
docs/         design specs
tests/        pytest tests (use their own fixture CSVs)
```

Amounts are integer cents. Timestamps are ISO-8601 UTC.

---

**Practicing for an interview?** Start with [EXERCISES.md](EXERCISES.md).
Don't open `answers/` until you've done an exercise out loud.
