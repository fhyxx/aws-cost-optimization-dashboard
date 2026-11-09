from __future__ import annotations

import pandas as pd

from aws_cost_dashboard.anomalies import detect_cost_anomalies


def make_series(spends: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "billing_month": f"2025-{index:02d}",
                "account": "demo-commerce",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": spend,
            }
            for index, spend in enumerate(spends, start=1)
        ]
    )


def test_explainable_rule_flags_monthly_spike() -> None:
    anomalies = detect_cost_anomalies(make_series([100, 105, 98, 102, 350]))
    assert len(anomalies) == 1
    row = anomalies.iloc[0]
    assert row["billing_month"] == "2025-05"
    assert row["change_usd"] == 248.0
    assert "MoM spike" in row["rule"]
    assert "not a root-cause finding" in row["explanation"]


def test_stable_months_do_not_flag() -> None:
    assert detect_cost_anomalies(make_series([100, 103, 98, 102, 105])).empty


def test_sample_dataset_contains_introduced_anomalies() -> None:
    from aws_cost_dashboard.sample_data import load_sample_data

    frame = load_sample_data()
    found = detect_cost_anomalies(frame)
    assert "2026-04" in set(found["billing_month"])
    assert "2026-02" in set(found["billing_month"])
