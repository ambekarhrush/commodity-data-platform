"""Compare full snapshots before promoting a new source download."""

import pandas as pd


def compare(previous: pd.DataFrame | None, current: pd.DataFrame) -> dict:
    if previous is None:
        return {"added": len(current), "revised": 0, "removed": 0, "revision_sample": []}
    keys = ["source", "series", "date"]
    old = previous.copy()
    new = current.copy()
    old["date"] = pd.to_datetime(old.date)
    new["date"] = pd.to_datetime(new.date)
    joined = old.merge(
        new, on=keys, how="outer", suffixes=("_old", "_new"), indicator=True, validate="one_to_one"
    )
    if (joined._merge == "left_only").any():
        raise ValueError("Snapshot lost historical observations or an entire series")
    both = joined[joined._merge == "both"]
    for col in ["unit", "frequency", "kind", "dimensions"]:
        if f"{col}_old" not in both or f"{col}_new" not in both:
            continue
        if (both[f"{col}_old"] != both[f"{col}_new"]).any():
            raise ValueError("Existing series metadata changed; explicit migration required")
    revised = both[both.value_old != both.value_new]
    sample = revised[keys + ["value_old", "value_new"]].head(50).copy()
    sample["date"] = sample.date.dt.strftime("%Y-%m-%d")
    return {
        "added": int((joined._merge == "right_only").sum()),
        "revised": len(revised),
        "removed": 0,
        "revision_sample": sample.to_dict(orient="records"),
    }
