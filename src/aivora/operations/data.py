"""Deterministic CSV tools. No model-generated Python or SQL is executed."""

import csv
import io
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_

from .models import Dataset


def dataset_visible(user):
    clauses = [
        Dataset.visibility == "organization",
        (Dataset.visibility == "department") & (Dataset.department == user.department),
    ]
    if user.role == "admin":
        clauses.append(Dataset.visibility == "admin")
    return or_(*clauses)


def number(value):
    try:
        result = Decimal(value.strip())
        return result if result.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None


def decimal_text(value):
    return (
        format(value.quantize(Decimal("0.0001")), "f").rstrip("0").rstrip(".")
        if value != 0
        else "0"
    )


def read_csv(content):
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("CSV is limited to 2 MB")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
    columns = reader.fieldnames or []
    if (
        not columns
        or len(columns) > 60
        or len(set(columns)) != len(columns)
        or any(not c.strip() or len(c) > 100 for c in columns)
    ):
        raise ValueError("Use 1-60 unique, nonempty column names (max 100 characters)")
    rows = []
    for row in reader:
        if None in row or any(value is None or len(value) > 2000 for value in row.values()):
            raise ValueError("CSV has inconsistent columns or a cell longer than 2,000 characters")
        rows.append({key: value.strip() for key, value in row.items()})
        if len(rows) > 10000:
            raise ValueError("CSV is limited to 10,000 rows")
    if not rows:
        raise ValueError("CSV has no data rows")
    return columns, rows, profile(columns, rows)


def profile(columns, rows, group_by="", metric=""):
    result = {"row_count": len(rows), "columns": {}, "groups": []}
    for column in columns:
        values = [r[column] for r in rows if r[column] != ""]
        numeric = [number(v) for v in values]
        is_numeric = bool(values) and all(v is not None for v in numeric)
        record = {
            "missing": len(rows) - len(values),
            "unique": len(set(values)),
            "type": "numeric" if is_numeric else "text",
        }
        if is_numeric:
            try:
                total = sum(numeric, Decimal(0))
                record.update(
                    min=decimal_text(min(numeric)),
                    max=decimal_text(max(numeric)),
                    total=decimal_text(total),
                    mean=decimal_text(total / len(numeric)),
                )
            except (InvalidOperation, OverflowError):
                record["type"] = "text"
                record["note"] = "Numeric magnitude exceeds analysis limits"
        elif len(set(values)) <= 40:
            record["categories"] = [
                {"label": k, "count": v} for k, v in Counter(values).most_common(12)
            ]
        result["columns"][column] = record
    if group_by:
        if (
            group_by not in columns
            or metric
            and (metric not in columns or result["columns"][metric]["type"] != "numeric")
        ):
            raise ValueError("Select a valid group column and a numeric metric")
        grouped = defaultdict(list)
        for row in rows:
            grouped[row[group_by] or "(missing)"].append(row)
        if len(grouped) > 100:
            raise ValueError("Group-by is limited to 100 distinct groups")
        for key, group in grouped.items():
            entry = {
                "label": key,
                "count": len(group),
                "row_share_percent": decimal_text(Decimal(len(group)) * 100 / len(rows)),
            }
            if metric:
                numbers = [number(r[metric]) for r in group if r[metric]]
                entry["total"] = decimal_text(sum(numbers, Decimal(0)))
                entry["mean"] = (
                    decimal_text(sum(numbers, Decimal(0)) / len(numbers)) if numbers else None
                )
                overall = sum((number(r[metric]) or Decimal(0)) for r in rows)
                entry["metric_share_percent"] = (
                    decimal_text(sum(numbers, Decimal(0)) * 100 / overall) if overall else None
                )
            result["groups"].append(entry)
        result["groups"].sort(key=lambda x: x["count"], reverse=True)
        result["group_by"], result["metric"] = group_by, metric
    return result
