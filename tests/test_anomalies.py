from __future__ import annotations

import pandas as pd
import pytest

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
    assert "does not identify root cause" in row["explanation"]


def test_stable_months_do_not_flag() -> None:
    assert detect_cost_anomalies(make_series([100, 103, 98, 102, 105])).empty


def test_sample_dataset_contains_introduced_anomalies() -> None:
    from aws_cost_dashboard.sample_data import load_sample_data

    frame = load_sample_data()
    found = detect_cost_anomalies(frame)
    assert "2026-04" in set(found["billing_month"])
    assert "2026-02" in set(found["billing_month"])


def test_median_only_anomaly_uses_median_deviation_for_ranking() -> None:
    # The final month is flat MoM, but is twice the prior-history median.
    anomalies = detect_cost_anomalies(
        make_series([100, 100, 100, 200, 200]),
        percent_threshold=50,
        minimum_increase_usd=100,
    )
    row = anomalies.loc[anomalies["billing_month"] == "2025-05"].iloc[0]
    assert row["rule"] == "rolling-median spike"
    assert row["change_usd"] == 0.0
    assert row["anomaly_increase_usd"] == 100.0
    assert row["change_percent"] == 0.0


def test_missing_month_is_not_mistaken_for_previous_month() -> None:
    frame = make_series([100, 100, 100, 500]).drop(index=3).copy()
    frame.loc[len(frame)] = {
        "billing_month": "2025-05",
        "account": "demo-commerce",
        "region": "us-east-1",
        "service": "Amazon EC2",
        "unblended_cost": 500.0,
    }
    found = detect_cost_anomalies(frame, percent_threshold=50, minimum_increase_usd=100)
    may = found.loc[found["billing_month"] == "2025-05"].iloc[0]
    assert may["previous_month_usd"] is None
    assert "MoM spike" not in may["rule"]
    assert "rolling-median spike" in may["rule"]
    assert may["confidence"] == "Low"


@pytest.mark.parametrize(
    "overrides",
    [
        {"history_months": 0},
        {"minimum_increase_usd": -1},
        {"percent_threshold": float("nan")},
        {"median_multiple": 0},
    ],
)
def test_invalid_anomaly_rule_configuration_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="Anomaly thresholds"):
        detect_cost_anomalies(make_series([100, 200]), **overrides)  # type: ignore[arg-type]
