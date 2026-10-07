"""Materialized, date-aligned derived observations with input snapshot lineage."""

import json
from pathlib import Path

import duckdb
import pandas as pd

from commodity_data.connectors import COLUMNS, Download
from commodity_data.public_sources import METALS


class Derived:
    name = "derived"

    def __init__(self, root: Path):
        self.root = root

    def fetch(self) -> Download:
        with duckdb.connect(str(self.root / "catalog.duckdb"), read_only=True) as con:
            frame = con.execute(
                "SELECT * FROM observations WHERE source IN ('eia-public', 'westmetall')"
            ).fetchdf()
        if frame.empty:
            raise ValueError("Ingest EIA public or Westmetall data before deriving series")
        return Download(
            frame.to_json(orient="records", date_format="iso").encode(),
            "local://observations?method=derived-v1",
            "json",
        )

    def parse(self, raw: bytes) -> pd.DataFrame:
        data = pd.DataFrame(json.loads(raw))
        records: list[tuple] = []
        self.lineage: dict = {}

        def align(source: str, inputs: list[str], expected_units: list[str]) -> pd.DataFrame | None:
            subset = data[(data.source == source) & data.series.isin(inputs)]
            if subset.empty:
                return None
            if set(subset.series) != set(inputs):
                raise ValueError("Missing derived input series")
            for series, unit in zip(inputs, expected_units):
                if set(subset[subset.series == series].unit) != {unit}:
                    raise ValueError("Derived input units do not match specification")
            wide = subset.pivot(index="date", columns="series", values="value")[inputs].dropna()
            if wide.empty:
                raise ValueError("No overlapping observations for derived series")
            self.lineage[source] = sorted(set(subset.run_id))
            return wide

        def add(name: str, values: pd.Series, unit: str, kind: str) -> None:
            for dt, value in values.items():
                records.append(
                    (
                        self.name,
                        name,
                        pd.Timestamp(str(dt)).date(),
                        float(value),
                        unit,
                        "daily",
                        kind,
                    )
                )

        for symbol in METALS:
            cash, forward = f"LME_{symbol}_cash", f"LME_{symbol}_3m"
            wide = align("westmetall", [cash, forward], ["USD/tonne", "USD/tonne"])
            if wide is not None:
                add(
                    f"LME_{symbol}_cash_minus_3m", wide[cash] - wide[forward], "USD/tonne", "spread"
                )
                positive = wide[wide[cash] > 0]
                add(
                    f"LME_{symbol}_relative_3m_slope",
                    (positive[forward] - positive[cash]) / positive[cash],
                    "fraction",
                    "relative_slope",
                )
        crude, gas, heat = "RWTC", "EER_EPMRU_PF4_Y35NY_DPG", "EER_EPD2F_PF4_Y35NY_DPG"
        wide = align("eia-public", [crude, gas, heat], ["USD/bbl", "USD/gal", "USD/gal"])
        if wide is not None:
            add(
                "indicative_spot_crack_321",
                (2 * 42 * wide[gas] + 42 * wide[heat] - 3 * wide[crude]) / 3,
                "USD/bbl",
                "indicative_spot_spread",
            )
        wide = align("eia-public", ["RCLC1", "RCLC2"], ["USD/bbl", "USD/bbl"])
        if wide is not None:
            add(
                "WTI_rank1_minus_rank2_historical",
                wide.RCLC1 - wide.RCLC2,
                "USD/bbl",
                "futures_rank_discontinued",
            )
        return pd.DataFrame(records, columns=COLUMNS)
