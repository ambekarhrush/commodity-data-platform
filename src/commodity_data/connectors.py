"""Source adapters. Observation dates are not publication timestamps."""

import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

import httpx
import pandas as pd

WB_URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
EIA_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
COLUMNS = ["source", "series", "date", "value", "unit", "frequency", "kind"]


@dataclass
class Download:
    raw: bytes
    url: str
    extension: str


class Connector(Protocol):
    name: str

    def fetch(self) -> Download: ...
    def parse(self, raw: bytes) -> pd.DataFrame: ...


def client() -> httpx.Client:
    return httpx.Client(timeout=90, follow_redirects=True, transport=httpx.HTTPTransport(retries=3))


class WorldBank:
    name = "worldbank"

    def fetch(self) -> Download:
        with client() as session:
            response = session.get(WB_URL)
            response.raise_for_status()
        return Download(response.content, WB_URL, "xlsx")

    def parse(self, raw: bytes) -> pd.DataFrame:
        sheet = pd.read_excel(BytesIO(raw), sheet_name="Monthly Prices", header=None)
        starts = [
            i
            for i, value in enumerate(sheet.iloc[:, 0])
            if re.fullmatch(r"\d{4}M\d{2}", str(value).strip())
        ]
        if not starts:
            raise ValueError("World Bank schema changed: no monthly rows")
        first = starts[0]
        # Header/unit rows immediately precede the monthly observations.
        names = sheet.iloc[first - 2]
        units = sheet.iloc[first - 1]
        records = []
        for row in sheet.iloc[starts].itertuples(index=False, name=None):
            period = str(row[0]).strip()
            date = pd.Period(period.replace("M", "-"), freq="M").end_time.date()
            for col in range(1, len(row)):
                if pd.isna(names.iloc[col]):
                    continue
                if pd.isna(row[col]) or str(row[col]).strip() in {"…", "..", "..."}:
                    continue
                value = float(row[col])
                records.append(
                    (
                        self.name,
                        str(names.iloc[col]).strip(),
                        date,
                        float(value),
                        str(units.iloc[col]).strip(),
                        "monthly",
                        "benchmark",
                    )
                )
        return pd.DataFrame(records, columns=COLUMNS)


class EIA:
    name = "eia"

    def fetch(self) -> Download:
        key = os.environ.get("EIA_API_KEY")
        if not key:
            raise ValueError("Set EIA_API_KEY to enable EIA ingestion")
        rows = []
        offset = 0
        with client() as session:
            while True:
                params = {
                    "api_key": key,
                    "frequency": "daily",
                    "data[0]": "value",
                    "facets[series][0]": "RWTC",
                    "facets[series][1]": "RBRTE",
                    "sort[0][column]": "period",
                    "sort[0][direction]": "asc",
                    "offset": str(offset),
                    "length": "5000",
                }
                response = session.get(EIA_URL, params=params)
                # Never include request URLs: they contain credentials.
                if response.status_code != 200:
                    raise ValueError(f"EIA HTTP status {response.status_code}")
                payload = response.json()["response"]
                page = payload["data"]
                if not page and offset < int(payload["total"]):
                    raise ValueError("Incomplete EIA pagination")
                rows.extend(page)
                offset += len(page)
                if offset >= int(payload["total"]):
                    break
        return Download(json.dumps(rows).encode(), EIA_URL, "json")

    def parse(self, raw: bytes) -> pd.DataFrame:
        records = []
        for row in json.loads(raw):
            value = pd.to_numeric(row["value"], errors="coerce")
            if pd.isna(value):
                continue
            records.append(
                (
                    self.name,
                    row["series"],
                    pd.Timestamp(row["period"]).date(),
                    float(value),
                    row["units"],
                    "daily",
                    "spot",
                )
            )
        return pd.DataFrame(records, columns=COLUMNS)
