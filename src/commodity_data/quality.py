"""Blocking structural checks and non-blocking research alerts."""

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from commodity_data.connectors import COLUMNS


def validate(frame: pd.DataFrame) -> None:
    if frame.empty or not set(COLUMNS).issubset(frame.columns):
        raise ValueError("Empty observations or missing schema columns")
    if frame[COLUMNS].isna().any().any():
        raise ValueError("Null required fields")
    if frame.duplicated(["source", "series", "date"]).any():
        raise ValueError("Duplicate observation keys")
    if not np.isfinite(frame.value.to_numpy(dtype=float)).all():
        raise ValueError("Non-finite prices")
    if (pd.to_datetime(frame.date).dt.date > datetime.now(UTC).date()).any():
        raise ValueError("Future observation dates")
    for _, group in frame.groupby(["source", "series"]):
        if any(group[col].nunique() != 1 for col in ["unit", "frequency", "kind"]):
            raise ValueError("Inconsistent series metadata")
        if group.frequency.iloc[0] not in {"daily", "weekly", "monthly"}:
            raise ValueError("Unsupported frequency")


def alerts(frame: pd.DataFrame, today: date) -> list[dict[str, str]]:
    result = []
    for (source, series), group in frame.groupby(["source", "series"]):
        ordered = group.sort_values("date")
        dates = pd.to_datetime(ordered.date)
        monthly = ordered.frequency.iloc[0] == "monthly"
        age = (today - dates.iloc[-1].date()).days

        def add(
            check: str,
            message: str,
            evidence: str,
            source: str = str(source),
            series: str = str(series),
        ) -> None:
            result.append(
                {
                    "source": str(source),
                    "series": str(series),
                    "check": check,
                    "message": message,
                    "evidence": evidence,
                }
            )

        if ordered.kind.iloc[0] not in {"futures_rank_discontinued", "wasde_estimate"} and age > (
            65 if monthly else (14 if ordered.frequency.iloc[0] == "weekly" else 7)
        ):
            add(
                "stale",
                f"Latest observation is {age} calendar days old",
                str(dates.iloc[-1].date()),
            )
        if ordered.kind.iloc[0] == "wasde_estimate":
            # A marketing-year estimate legitimately stops appearing after its
            # balance sheet rolls off the monthly report. Release completeness is
            # checked at the source-file level instead of assuming price-like gaps.
            continue
        if monthly:
            gaps = dates.dt.year * 12 + dates.dt.month
            gap_mask = gaps.diff() > 1
        else:
            # Conservative calendar-day heuristic, not an exchange holiday calendar.
            gap_mask = dates.diff().dt.days > (14 if ordered.frequency.iloc[0] == "weekly" else 7)
        count = int(gap_mask.sum())
        if count:
            add(
                "gaps",
                f"{count} internal gaps; no prices were filled",
                ",".join(dates[gap_mask].dt.strftime("%Y-%m-%d")),
            )
        previous = ordered.value.shift(1)
        changes = (ordered.value - previous).abs() / previous.abs().clip(lower=1e-8)
        count = int((changes > 0.5).sum())
        if count:
            add(
                "outlier",
                f"{count} moves exceed 50%; review, do not delete automatically",
                ",".join(dates[changes > 0.5].dt.strftime("%Y-%m-%d")),
            )
    return result
