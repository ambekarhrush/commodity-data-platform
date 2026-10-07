"""Single-market settlement curves. Inputs must share currency and price units."""

from typing import cast

import numpy as np
import pandas as pd


def calendar_spread(near: float, far: float) -> float:
    return near - far


def crack_321(
    crude_per_barrel: float, gasoline_per_gallon: float, heating_oil_per_gallon: float
) -> float:
    """Indicative 3:2:1 gross refining spread, USD per barrel of crude."""
    return (2 * 42 * gasoline_per_gallon + 42 * heating_oil_per_gallon - 3 * crude_per_barrel) / 3


def annualized_slope(near: float, far: float, days: int) -> float:
    """Annualized log far/near slope; positive means contango."""
    if near <= 0 or far <= 0 or days <= 0:
        raise ValueError("Log slope requires positive prices and tenor")
    return float(np.log(far / near) * 365 / days)


def continuous(
    frame: pd.DataFrame,
    roll_days: int = 5,
    *,
    basis: str = "calendar",
    holidays: list[str] | None = None,
    adjustment: str = "additive",
) -> pd.DataFrame:
    """Roll N calendar days before expiry; additive backward adjustment.

    Columns: date, contract, expiry, settle. One market and consistent units only.
    A new contract becomes active at the close on the roll date. P&L on that
    date uses the OLD contract's settlement change. No interpolation is allowed.
    Back-adjusted levels are revised with future rolls, so use held_change for P&L.
    """
    if roll_days < 0 or frame.empty:
        raise ValueError("Need quotes and nonnegative roll_days")
    if basis not in {"calendar", "business"} or adjustment not in {"additive", "none"}:
        raise ValueError("Unsupported roll basis or adjustment")
    required = {"date", "contract", "expiry", "settle"}
    if not required.issubset(frame.columns) or frame[list(required)].isna().any().any():
        raise ValueError("Missing contract schema or null required fields")
    quotes = frame.copy()
    for col in ["date", "expiry"]:
        quotes[col] = pd.to_datetime(quotes[col])
    if quotes.duplicated(["date", "contract"]).any():
        raise ValueError("Duplicate contract/date")
    if not np.isfinite(quotes.settle.to_numpy(dtype=float)).all():
        raise ValueError("Invalid settlement")
    if quotes.groupby("contract").expiry.nunique().max() != 1:
        raise ValueError("Contract expiry changed")
    if (quotes.date > quotes.expiry).any():
        raise ValueError("Quote after expiry")
    metadata = quotes[["contract", "expiry"]].drop_duplicates().sort_values("expiry")
    if metadata.expiry.duplicated().any():
        raise ValueError("Ambiguous expiry ordering")
    if "first_notice" in quotes:
        quotes["first_notice"] = pd.to_datetime(quotes.first_notice)
        if quotes.groupby("contract").first_notice.nunique(dropna=False).max() != 1:
            raise ValueError("Contract first-notice date changed")
        notice = quotes[["contract", "first_notice"]].drop_duplicates()
        metadata = metadata.merge(notice, on="contract", validate="one_to_one")
        metadata["cutoff"] = metadata[["expiry", "first_notice"]].min(axis=1)
    else:
        metadata["cutoff"] = metadata.expiry
    if basis == "business":
        day_calendar = np.busdaycalendar(holidays=np.array(holidays or [], dtype="datetime64[D]"))
        metadata["roll_date"] = [
            pd.Timestamp(
                np.busday_offset(d.date(), -roll_days, roll="backward", busdaycal=day_calendar)
            )
            for d in metadata.cutoff
        ]
        expected = pd.date_range(
            quotes.date.min(),
            quotes.date.max(),
            freq=pd.offsets.CustomBusinessDay(holidays=holidays or []),
        )
        if set(quotes.date) != set(expected):
            raise ValueError("Quotes missing a business session or include a non-session date")
    else:
        metadata["roll_date"] = metadata.cutoff - pd.Timedelta(days=roll_days)
    records = []
    old_contract = None
    previous_settle = None
    for day_key, group in quotes.groupby("date", sort=True):
        day = cast(pd.Timestamp, day_key)
        eligible = metadata[metadata.roll_date > day]
        if eligible.empty:
            raise ValueError("Insufficient forward contracts for roll rule")
        chosen = eligible.iloc[0]
        prices = group.set_index("contract").settle
        if chosen.contract not in prices:
            raise ValueError("Missing scheduled contract quote")
        price = float(prices[chosen.contract])
        gap = 0.0
        change = np.nan
        if old_contract is not None:
            if old_contract not in prices:
                raise ValueError("Missing held contract on roll/valuation date")
            change = float(prices[old_contract]) - float(cast(float, previous_settle))
            if chosen.contract != old_contract:
                gap = price - float(prices[old_contract])
        records.append(
            {
                "date": day,
                "contract": chosen.contract,
                "settle": price,
                "roll_gap": gap,
                "held_change": change,
            }
        )
        old_contract, previous_settle = chosen.contract, price
    result = pd.DataFrame(records)
    result["back_adjusted"] = (
        result.settle + result.roll_gap.iloc[::-1].cumsum().iloc[::-1] - result.roll_gap
    )
    result["continuous_price"] = result.back_adjusted if adjustment == "additive" else result.settle
    result["adjustment"] = adjustment
    return result
