"""Shared guard for the verify_m*.py scripts.

These checks clear the document index, delete memories and schedules, wipe the activity ledger
and write exports, so they must never run against the real Loki on port 8420. `run_tests.py`
starts a separate Loki server with a throwaway data folder and passes its URL and folder here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def base_url() -> str:
    url = os.environ.get("LOKI_TEST_URL", "").strip()
    if not url:
        sys.exit(
            "Refusing to run: this check changes Loki's stored data.\n"
            "Run it through the isolated runner instead, which uses a separate server and a\n"
            "throwaway data folder:\n"
            "    python tests/run_tests.py            (all suites)\n"
            "    python tests/run_tests.py m3 m8      (selected suites)"
        )
    return url


def test_data_dir() -> Path:
    """The isolated server's data folder (never the project's real `data/`)."""
    return Path(os.environ["LOKI_TEST_DATA_DIR"])
