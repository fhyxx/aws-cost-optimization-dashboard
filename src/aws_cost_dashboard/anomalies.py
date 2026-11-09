"""Explainable billing-spike detection using month-over-month and rolling-median rules."""

from __future__ import annotations

import math

import pandas as pd

_GROUP_COLUMNS = ["account", "region", "service"]


def detect_cost_anomalies(
    frame: pd.DataFrame,
    *,
    percent_threshold: float = 50.0,
    minimum_increase_usd: float = 100.0,
    median_multiple: float = 1.5,
    history_months: int = 6,
) -> pd.DataFrame:
    """Flag unusually high monthly charges and explain the rule and comparison values.

    A row is flagged when it is at least the dollar threshold above either the previous
    month by ``percent_threshold`` or the prior-history median by ``median_multiple``.
    Only earlier months are used as the baseline.
    """
    columns = [
        "billing_month",
        *_GROUP_COLUMNS,
        "actual_usd",
        "previous_month_usd",
        "history_median_usd",
        "change_usd",
        "anomaly_increase_usd",
        "change_percent",
        "rule",
        "rule_agreement",
        "confidence",
        "explanation",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    thresholds = (percent_threshold, minimum_increase_usd, median_multiple)
    if (
        history_months < 1
        or any(not math.isfinite(value) for value in thresholds)
        or minimum_increase_usd < 0
        or percent_threshold < 0
        or median_multiple <= 0
    ):
        raise ValueError(
            "Anomaly thresholds must be finite and non-negative, median_multiple must be positive, "
            "and history_months must be positive."
        )

    monthly = frame.groupby([*_GROUP_COLUMNS, "billing_month"], as_index=False).agg(
        actual_usd=("unblended_cost", "sum")
    )
    output: list[dict[str, object]] = []
    for key, group in monthly.groupby(_GROUP_COLUMNS, sort=False):
        series = group.sort_values("billing_month").reset_index(drop=True)
        periods = series["billing_month"].map(lambda month: pd.Period(str(month), freq="M"))
        for index in range(len(series)):
            current = series.iloc[index]
            current_period = periods.iloc[index]
            prior_mask = (periods >= current_period - history_months) & (periods < current_period)
            prior = series.loc[prior_mask]
            previous_mask = periods == current_period - 1
            previous_rows = series.loc[previous_mask]
            previous = (
                float(previous_rows.iloc[0]["actual_usd"]) if not previous_rows.empty else None
            )
            actual = float(current["actual_usd"])
            median = float(prior["actual_usd"].median()) if not prior.empty else 0.0
            mom_delta = actual - previous if previous is not None else None
            percent = (
                mom_delta / previous * 100
                if mom_delta is not None and previous is not None and previous > 0
                else None
            )
            mom_flag = (
                mom_delta is not None
                and percent is not None
                and percent >= percent_threshold
                and mom_delta >= minimum_increase_usd
            )
            median_delta = actual - median
            median_flag = (
                len(prior) >= min(3, history_months)
                and median > 0
                and actual >= median * median_multiple
                and median_delta >= minimum_increase_usd
            )
            if not (mom_flag or median_flag):
                continue
            # Rank a flagged row by the increase against the baseline(s) that
            # actually triggered it, not by an unrelated MoM delta.
            qualifying_deltas = [
                value
                for value, triggered in ((mom_delta, mom_flag), (median_delta, median_flag))
                if triggered and value is not None
            ]
            anomaly_increase = max(qualifying_deltas)
            rules: list[str] = []
            if mom_flag:
                rules.append("MoM spike")
            if median_flag:
                rules.append("rolling-median spike")
            account, region, service = key
            output.append(
                {
                    "billing_month": str(current["billing_month"]),
                    "account": account,
                    "region": region,
                    "service": service,
                    "actual_usd": round(actual, 2),
                    "previous_month_usd": round(previous, 2) if previous is not None else None,
                    "history_median_usd": round(median, 2),
                    "change_usd": round(mom_delta if mom_delta is not None else median_delta, 2),
                    "anomaly_increase_usd": round(anomaly_increase, 2),
                    "change_percent": round(percent, 2) if percent is not None else None,
                    "rule": " + ".join(rules),
                    "rule_agreement": "Both rules" if len(rules) == 2 else "One rule",
                    "confidence": "Low",
                    "explanation": (
                        f"{service} in {account} / {region} billed ${actual:,.2f} in "
                        f"{current['billing_month']}; the calendar prior-month value is "
                        f"{'$' + format(previous, ',.2f') if previous is not None else 'unavailable'}. "
                        f"The prior {history_months} calendar-month window contains "
                        f"{len(prior)} observed month(s), with a median of ${median:,.2f}. "
                        f"Rule(s): {' + '.join(rules)}. Rule agreement is not statistical confidence; "
                        "this billing pattern needs investigation and does not identify root cause."
                    ),
                }
            )
    if not output:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(output, columns=columns)
        .sort_values(["billing_month", "change_usd"], ascending=[False, False])
        .reset_index(drop=True)
    )
