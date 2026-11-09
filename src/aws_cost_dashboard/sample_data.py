"""Load the reproducible synthetic demonstration dataset."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from aws_cost_dashboard.schemas import validate_billing_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_aws_costs.csv"


def load_sample_data() -> pd.DataFrame:
    """Load and validate checked-in synthetic demonstration billing data."""
    raw = pd.read_csv(SAMPLE_DATA_PATH)
    return validate_billing_data(raw)
