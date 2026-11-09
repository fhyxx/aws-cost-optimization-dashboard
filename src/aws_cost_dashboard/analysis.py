"""Billing-derived aggregations and executive metrics."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExecutiveMetrics:
    """Summary metrics for the selected billing records."""

    period_total: float
    current_month: str
    current_month_spend: float
    previous_month: str | None
    previous_month_spend: float | None
    month_over_month_change: float | None
    month_over_month_percent: float | None


def monthly_totals(frame: pd.DataFrame) -> pd.DataFrame:
    """Return monthly totals with absent calendar months represented as unknown (NaN)."""
    if frame.empty:
        return pd.DataFrame(columns=["billing_month", "spend"])
    observed = (
        frame.groupby("billing_month", as_index=False)
        .agg(spend=("unblended_cost", "sum"))
        .sort_values("billing_month")
        .reset_index(drop=True)
    )
    periods = pd.period_range(
        observed["billing_month"].iloc[0], observed["billing_month"].iloc[-1], freq="M"
    )
    result = (
        observed.set_index("billing_month")
        .reindex(periods.astype(str))
        .rename_axis("billing_month")
        .reset_index()
    )
    result["spend"] = result["spend"].round(2)
    return result


def executive_metrics(frame: pd.DataFrame) -> ExecutiveMetrics:
    """Calculate total spend and month-over-month change from available billing rows."""
    totals = monthly_totals(frame)
    if totals.empty:
        return ExecutiveMetrics(0.0, "—", 0.0, None, None, None, None)
    current = totals.iloc[-1]
    current_period = pd.Period(str(current["billing_month"]), freq="M")
    prior_month = str(current_period - 1)
    previous_rows = totals[totals["billing_month"] == prior_month]
    previous = (
        previous_rows.iloc[0]
        if not previous_rows.empty and pd.notna(previous_rows.iloc[0]["spend"])
        else None
    )
    current_spend = float(current["spend"])
    previous_spend = float(previous["spend"]) if previous is not None else None
    delta = current_spend - previous_spend if previous_spend is not None else None
    percent = (
        delta / previous_spend * 100
        if delta is not None and previous_spend is not None and previous_spend > 0
        else None
    )
    return ExecutiveMetrics(
        period_total=round(float(totals["spend"].sum()), 2),
        current_month=str(current["billing_month"]),
        current_month_spend=round(current_spend, 2),
        previous_month=(
            prior_month
            if previous is not None
            or bool((totals["billing_month"] < current["billing_month"]).any())
            else None
        ),
        previous_month_spend=round(previous_spend, 2) if previous_spend is not None else None,
        month_over_month_change=round(delta, 2) if delta is not None else None,
        month_over_month_percent=round(percent, 2) if percent is not None else None,
    )


def cost_breakdown(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Aggregate spend by a supported billing dimension."""
    allowed = {"service", "region", "account"}
    if dimension not in allowed:
        raise ValueError(f"Unsupported cost dimension {dimension!r}; choose {sorted(allowed)}.")
    if frame.empty:
        return pd.DataFrame(columns=[dimension, "spend"])
    return (
        frame.groupby(dimension, as_index=False)
        .agg(spend=("unblended_cost", "sum"))
        .sort_values("spend", ascending=False)
        .reset_index(drop=True)
    )


def monthly_breakdown(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Return spend over time for one supported billing dimension."""
    if dimension not in {"service", "region", "account"}:
        raise ValueError(f"Unsupported cost dimension: {dimension}")
    if frame.empty:
        return pd.DataFrame(columns=["billing_month", dimension, "spend"])
    return (
        frame.groupby(["billing_month", dimension], as_index=False)
        .agg(spend=("unblended_cost", "sum"))
        .sort_values("billing_month")
        .reset_index(drop=True)
    )
