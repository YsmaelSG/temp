import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import create_app  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def client(tmp_path):
    # Copy fixture CSVs so tests that write never touch the real data/ folder.
    for name in ("accounts.csv", "transactions.csv"):
        shutil.copy(os.path.join(FIXTURES, name), tmp_path / name)
    app = create_app(data_dir=str(tmp_path))
    app.config["TESTING"] = True
    app.config["DATA_DIR"] = str(tmp_path)
    return app.test_client()
