"""Input normalization and validation for monthly AWS billing records."""

from __future__ import annotations

import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class BillingRecord(BaseModel):
    """A normalized, monthly billing line used by the dashboard."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    billing_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    account: str = Field(min_length=1, max_length=128)
    region: str = Field(min_length=1, max_length=64)
    service: str = Field(min_length=1, max_length=128)
    unblended_cost: float = Field(allow_inf_nan=False)
    currency: Literal["USD"] = "USD"
    usage_quantity: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage_unit: str | None = None
    usage_type: str | None = None


_ALIASES: dict[str, tuple[str, ...]] = {
    "billing_month": ("billing_month", "month", "usage_month", "line_item_usage_start_date"),
    "account": (
        "account",
        "account_alias",
        "account_id",
        "line_item_usage_account_id",
        "linked_account_id",
    ),
    "region": ("region", "region_code", "product_region_code", "product_region"),
    "service": ("service", "service_name", "product_servicename", "line_item_product_code"),
    "unblended_cost": ("unblended_cost", "cost", "line_item_unblended_cost"),
    "currency": ("currency", "currency_code", "line_item_currency_code"),
    "usage_quantity": ("usage_quantity", "usage_amount", "line_item_usage_amount"),
    "usage_unit": ("usage_unit", "unit", "pricing_unit"),
    "usage_type": ("usage_type", "line_item_usage_type"),
}


def _account_label(value: Any) -> str:
    """Mask AWS account IDs for display while retaining a useful account grouping."""
    text = "" if pd.isna(value) else str(value).strip()
    if re.fullmatch(r"\d{12}", text):
        return f"AWS account ••••{text[-4:]}"
    return text


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = {str(column).strip().lower(): column for column in frame.columns}
    rename: dict[Any, str] = {}
    missing: list[str] = []
    for target, aliases in _ALIASES.items():
        source = next((normalized[name] for name in aliases if name in normalized), None)
        if source is None:
            if target in {"billing_month", "account", "region", "service", "unblended_cost"}:
                missing.append(f"{target} (accepted headers: {', '.join(aliases)})")
        else:
            rename[source] = target
    if missing:
        raise ValueError("Missing required billing columns: " + "; ".join(missing) + ".")

    result = frame.rename(columns=rename).copy()
    duplicate_columns = result.columns[result.columns.duplicated()].tolist()
    if duplicate_columns:
        duplicate_names = ", ".join(sorted(set(map(str, duplicate_columns))))
        raise ValueError(
            f"Ambiguous duplicate billing columns after alias mapping: {duplicate_names}."
        )
    if "billing_month" in result.columns:
        values = result["billing_month"]
        if pd.api.types.is_datetime64_any_dtype(values):
            result["billing_month"] = values.dt.strftime("%Y-%m")
        else:
            parsed = pd.to_datetime(values, errors="coerce", utc=True)
            month_values = parsed.dt.strftime("%Y-%m")
            # Already-normalized YYYY-MM values parse consistently; malformed rows stay NaN.
            result["billing_month"] = month_values
    if "usage_quantity" not in result.columns:
        result["usage_quantity"] = None
    if "usage_unit" not in result.columns:
        result["usage_unit"] = None
    if "usage_type" not in result.columns:
        result["usage_type"] = None
    if "currency" not in result.columns:
        result["currency"] = "USD"
    else:
        result["currency"] = result["currency"].astype("string").str.strip().str.upper()
    service_names = {
        "AmazonEC2": "Amazon EC2",
        "AmazonRDS": "Amazon RDS",
        "AmazonS3": "Amazon S3",
        "AmazonVPC": "Amazon VPC",
        "AmazonCloudWatch": "Amazon CloudWatch",
        "AmazonEBS": "Amazon EBS",
        "AWSLambda": "AWS Lambda",
    }
    result["service"] = result["service"].replace(service_names)
    result["account"] = result["account"].map(_account_label)
    result = result.astype(object).where(pd.notna(result), None)
    return result


def validate_billing_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a CSV data frame, reporting useful row-level errors."""
    if frame.empty:
        raise ValueError("The uploaded CSV contains no billing rows.")
    if len(frame) > 500_000:
        raise ValueError("The CSV contains more than 500,000 rows; upload a smaller date range.")

    normalized = _normalize_columns(frame)
    try:
        records = TypeAdapter(list[BillingRecord]).validate_python(
            normalized.to_dict(orient="records")
        )
    except ValidationError as exc:
        details: list[str] = []
        for error in exc.errors()[:12]:
            location = error.get("loc", ())
            row_number = int(location[0]) + 2 if location and isinstance(location[0], int) else "?"
            field = str(location[1]) if len(location) > 1 else "row"
            details.append(f"CSV row {row_number}, {field}: {error['msg']}.")
        suffix = " More errors omitted." if len(exc.errors()) > 12 else ""
        raise ValueError("Billing data failed validation: " + " ".join(details) + suffix) from exc

    validated = pd.DataFrame([record.model_dump() for record in records])
    validated["unblended_cost"] = validated["unblended_cost"].astype(float)
    validated["usage_quantity"] = pd.to_numeric(validated["usage_quantity"], errors="coerce")
    validated["billing_month"] = validated["billing_month"].astype(str)
    return validated.sort_values(["billing_month", "account", "region", "service"]).reset_index(
        drop=True
    )


def read_billing_csv(upload: Any) -> pd.DataFrame:
    """Read an uploaded CSV and translate parser failures into actionable messages."""
    try:
        raw = pd.read_csv(
            upload,
            dtype={"account_id": "string", "line_item_usage_account_id": "string"},
            nrows=500_001,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(
            "Could not read this CSV. Check that it is a UTF-8 comma-separated file with one header row."
        ) from exc
    return validate_billing_data(raw)
