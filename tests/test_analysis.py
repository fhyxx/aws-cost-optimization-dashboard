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


def test_missing_calendar_month_is_unknown_and_mom_is_not_calculated_across_gap() -> None:
    frame = sample_frame().query("billing_month == '2025-01'").copy()
    frame["billing_month"] = "2025-01"
    february = sample_frame().query("billing_month == '2025-02'").copy()
    february["billing_month"] = "2025-03"
    frame = pd.concat([frame, february], ignore_index=True)

    totals = monthly_totals(frame)
    assert totals["billing_month"].tolist() == ["2025-01", "2025-02", "2025-03"]
    assert pd.isna(totals.loc[totals["billing_month"] == "2025-02", "spend"]).all()
    metrics = executive_metrics(frame)
    assert metrics.period_total == 350.0
    assert metrics.current_month == "2025-03"
    assert metrics.previous_month == "2025-02"
    assert metrics.previous_month_spend is None
    assert metrics.month_over_month_change is None


def test_zero_prior_spend_has_delta_but_no_undefined_percent() -> None:
    frame = sample_frame().copy()
    frame.loc[frame["billing_month"] == "2025-01", "unblended_cost"] = 0.0
    result = executive_metrics(frame)
    assert result.month_over_month_change == 200.0
    assert result.month_over_month_percent is None


def test_identical_billing_lines_are_not_silently_deduplicated() -> None:
    frame = pd.concat([sample_frame().iloc[[0]], sample_frame().iloc[[0]]], ignore_index=True)
    assert monthly_totals(frame).iloc[0]["spend"] == 200.0


def test_dashboard_rollups_reconcile_to_monthly_period_total() -> None:
    frame = sample_frame()
    total = executive_metrics(frame).period_total
    assert monthly_totals(frame)["spend"].sum() == total
    for dimension in ("service", "region", "account"):
        assert round(float(cost_breakdown(frame, dimension)["spend"].sum()), 2) == total
