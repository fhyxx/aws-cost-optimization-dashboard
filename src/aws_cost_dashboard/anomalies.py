"""Explainable billing-spike detection using month-over-month and rolling-median rules."""

from __future__ import annotations

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
        "change_percent",
        "rule",
        "confidence",
        "explanation",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if history_months < 1 or minimum_increase_usd < 0 or percent_threshold < 0:
        raise ValueError(
            "Anomaly thresholds must be non-negative and history_months must be positive."
        )

    monthly = frame.groupby([*_GROUP_COLUMNS, "billing_month"], as_index=False).agg(
        actual_usd=("unblended_cost", "sum")
    )
    output: list[dict[str, object]] = []
    for key, group in monthly.groupby(_GROUP_COLUMNS, sort=False):
        series = group.sort_values("billing_month").reset_index(drop=True)
        for index in range(1, len(series)):
            prior = series.iloc[max(0, index - history_months) : index]
            current = series.iloc[index]
            previous = float(series.iloc[index - 1]["actual_usd"])
            actual = float(current["actual_usd"])
            median = float(prior["actual_usd"].median())
            delta = actual - previous
            percent = delta / previous * 100 if previous > 0 else None
            mom_flag = (
                percent is not None
                and percent >= percent_threshold
                and delta >= minimum_increase_usd
            )
            median_delta = actual - median
            median_flag = (
                median > 0
                and actual >= median * median_multiple
                and median_delta >= minimum_increase_usd
            )
            if not (mom_flag or median_flag):
                continue
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
                    "previous_month_usd": round(previous, 2),
                    "history_median_usd": round(median, 2),
                    "change_usd": round(delta, 2),
                    "change_percent": round(percent, 2) if percent is not None else None,
                    "rule": " + ".join(rules),
                    "confidence": "High" if len(rules) == 2 else "Medium",
                    "explanation": (
                        f"{service} in {account} / {region} rose by ${delta:,.2f} versus the prior month; "
                        f"the prior {len(prior)}-month median was ${median:,.2f}. "
                        f"Rule(s): {' + '.join(rules)}. This is a billing pattern to investigate, not a root-cause finding."
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
