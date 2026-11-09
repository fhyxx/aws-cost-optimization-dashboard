from __future__ import annotations

import pandas as pd

from aws_cost_dashboard.analysis import cost_breakdown, executive_metrics, monthly_totals


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "billing_month": "2025-01",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": 100.0,
            },
            {
                "billing_month": "2025-01",
                "account": "demo",
                "region": "us-west-2",
                "service": "Amazon S3",
                "unblended_cost": 50.0,
            },
            {
                "billing_month": "2025-02",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": 125.0,
            },
            {
                "billing_month": "2025-02",
                "account": "demo",
                "region": "us-west-2",
                "service": "Amazon S3",
                "unblended_cost": 75.0,
            },
        ]
    )


def test_monthly_totals_and_executive_metrics() -> None:
    frame = sample_frame()
    totals = monthly_totals(frame)
    assert totals.to_dict("records") == [
        {"billing_month": "2025-01", "spend": 150.0},
        {"billing_month": "2025-02", "spend": 200.0},
    ]
    result = executive_metrics(frame)
    assert result.period_total == 350.0
    assert result.current_month_spend == 200.0
    assert result.previous_month_spend == 150.0
    assert result.month_over_month_change == 50.0
    assert result.month_over_month_percent == 33.33


def test_breakdown_by_region_and_service() -> None:
    frame = sample_frame()
    by_service = cost_breakdown(frame, "service")
    assert by_service.iloc[0]["service"] == "Amazon EC2"
    assert by_service.iloc[0]["spend"] == 225.0
    assert cost_breakdown(frame, "region")["spend"].sum() == 350.0


def test_empty_metrics_are_safe() -> None:
    frame = sample_frame().iloc[0:0]
    assert monthly_totals(frame).empty
    assert executive_metrics(frame).period_total == 0
