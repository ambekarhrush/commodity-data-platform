"""Public downloads and the authenticated AGSI API; all adapters share one schema."""

import json
import os
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from bs4 import BeautifulSoup

from commodity_data.connectors import COLUMNS, Download, client
from commodity_data.transport import get

# Explicit instrument IDs, units and frequency; constant-maturity ranks are NOT contracts.
EIA_FILES = {
    "RWTC": ("d", "USD/bbl", "spot"),
    "RBRTE": ("d", "USD/bbl", "spot"),
    "EER_EPMRU_PF4_Y35NY_DPG": ("d", "USD/gal", "spot"),
    "EER_EPD2F_PF4_Y35NY_DPG": ("d", "USD/gal", "spot"),
    "WCESTUS1": ("w", "thousand bbl", "inventory"),
    "WCRFPUS2": ("w", "thousand bbl/day", "production"),
    "RCLC1": ("d", "USD/bbl", "futures_rank_discontinued"),
    "RCLC2": ("d", "USD/bbl", "futures_rank_discontinued"),
}
METALS = {
    "Cu": "Copper",
    "Al": "Aluminium",
    "Ni": "Nickel",
    "Zn": "Zinc",
    "Pb": "Lead",
    "Sn": "Tin",
}
CFTC_MARKETS = [
    "067651",
    "023651",
    "111659",
    "022651",
    "085692",
    "088691",
    "084691",
    "002602",
    "005602",
    "001602",
    "073732",
]
CFTC_FIELDS = ["open_interest_all", "m_money_positions_long_all", "m_money_positions_short_all"]
CFTC_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
AGSI_URL = "https://agsi.gie.eu/api"
FUTURES_CLOCK_EXPIRIES_URL = "https://futuresclock.com/data/expiries.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
WASDE_REQUIRED_COLUMNS = {
    "WasdeNumber",
    "ReportDate",
    "ReportTitle",
    "Attribute",
    "ReliabilityProjection",
    "Commodity",
    "Region",
    "MarketYear",
    "ProjEstFlag",
    "AnnualQuarterFlag",
    "Value",
    "Unit",
    "ReleaseDate",
    "ReleaseTime",
    "ForecastYear",
    "ForecastMonth",
}


def archive(files: dict[str, bytes]) -> bytes:
    result = BytesIO()
    with ZipFile(result, "w", ZIP_DEFLATED) as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return result.getvalue()


class EIAPublic:
    name = "eia-public"

    def fetch(self) -> Download:
        files = {}
        with client() as session:
            for series, (frequency, _, _) in EIA_FILES.items():
                url = f"https://www.eia.gov/dnav/pet/hist_xls/{series}{frequency}.xls"
                files[f"{series}.xls"] = get(session, url).content
        return Download(archive(files), "https://www.eia.gov/dnav/pet/", "zip")

    def parse(self, raw: bytes) -> pd.DataFrame:
        records = []
        with ZipFile(BytesIO(raw)) as z:
            for series, (frequency, unit, kind) in EIA_FILES.items():
                table = pd.read_excel(
                    BytesIO(z.read(f"{series}.xls")), sheet_name="Data 1", header=None
                )
                if str(table.iloc[1, 1]).strip() != series or table.shape[1] != 2:
                    raise ValueError("EIA workbook source key/schema mismatch")
                for dt, value in table.iloc[3:].itertuples(index=False, name=None):
                    if pd.isna(value):
                        continue
                    records.append(
                        (
                            self.name,
                            series,
                            pd.Timestamp(dt).date(),
                            float(value),
                            unit,
                            "daily" if frequency == "d" else "weekly",
                            kind,
                        )
                    )
        return pd.DataFrame(records, columns=COLUMNS)


class Westmetall:
    name = "westmetall"

    def __init__(self, since_year: int = 2020):
        if not 2008 <= since_year <= datetime.now(UTC).year:
            raise ValueError("Westmetall start year must be between 2008 and current year")
        self.since_year = since_year

    def fetch(self) -> Download:
        files = {}
        with client() as session:
            for symbol in METALS:
                for year in range(self.since_year, datetime.now(UTC).year + 1):
                    url = "https://www.westmetall.com/en/markdaten.php"
                    response = get(
                        session,
                        url,
                        params={
                            "action": "table",
                            "field": f"LME_{symbol}_cash",
                            "year": str(year),
                        },
                    )
                    files[f"{symbol}-{year}.html"] = response.content
        return Download(archive(files), "https://www.westmetall.com/en/markdaten.php", "zip")

    def parse(self, raw: bytes) -> pd.DataFrame:
        records = []
        with ZipFile(BytesIO(raw)) as z:
            for name in z.namelist():
                symbol, year_text = name.removesuffix(".html").split("-")
                metal = METALS[symbol]
                soup = BeautifulSoup(z.read(name), "html.parser")
                if f"LME {metal} Cash-Settlement" not in soup.get_text():
                    raise ValueError("Westmetall header changed")
                count = 0
                for row in soup.find_all("tr"):
                    cells = [c.get_text(strip=True) for c in row.find_all("td")]
                    if len(cells) != 4:
                        continue
                    dt = pd.to_datetime(cells[0], format="%d. %B %Y").date()
                    if dt.year != int(year_text):
                        raise ValueError("Westmetall returned wrong year")
                    for field, text, unit, kind in zip(
                        ["cash", "3m", "stock"],
                        cells[1:],
                        ["USD/tonne", "USD/tonne", "tonne"],
                        ["cash", "forward_3m", "inventory"],
                    ):
                        if text in {"", "-"}:
                            continue
                        value = float(text.replace(",", ""))
                        records.append(
                            (self.name, f"LME_{symbol}_{field}", dt, value, unit, "daily", kind)
                        )
                        count += 1
                if not count:
                    raise ValueError("Empty Westmetall year")
        return pd.DataFrame(records, columns=COLUMNS)


class CFTC:
    name = "cftc"

    def fetch(self) -> Download:
        select = [
            "id",
            "cftc_contract_market_code",
            "market_and_exchange_names",
            "report_date_as_yyyy_mm_dd",
            "contract_units",
            "futonly_or_combined",
            *CFTC_FIELDS,
        ]
        where = "cftc_contract_market_code in (" + ",".join(f"'{c}'" for c in CFTC_MARKETS) + ")"
        rows: list[dict] = []
        with client() as session:
            total = int(
                get(session, CFTC_URL, params={"$select": "count(*)", "$where": where}).json()[0][
                    "count"
                ]
            )
            while len(rows) < total:
                page = get(
                    session,
                    CFTC_URL,
                    params={
                        "$select": ",".join(select),
                        "$where": where,
                        "$order": "report_date_as_yyyy_mm_dd,id",
                        "$offset": str(len(rows)),
                        "$limit": "5000",
                    },
                ).json()
                if not page:
                    raise ValueError("Incomplete CFTC pagination")
                rows.extend(page)
        if len(rows) != total:
            raise ValueError("CFTC changed during pagination; retry snapshot")
        return Download(json.dumps(rows).encode(), CFTC_URL, "json")

    def parse(self, raw: bytes) -> pd.DataFrame:
        records = []
        for row in json.loads(raw):
            if row["futonly_or_combined"] != "FutOnly":
                raise ValueError("Expected disaggregated futures-only COT")
            code = row["cftc_contract_market_code"]
            dt = pd.Timestamp(row["report_date_as_yyyy_mm_dd"]).date()
            for field in CFTC_FIELDS:
                records.append(
                    (
                        self.name,
                        f"{code}:{field}",
                        dt,
                        float(row[field]),
                        "contracts",
                        "weekly",
                        "positioning",
                    )
                )
        frame = pd.DataFrame(records, columns=COLUMNS)
        expected = {f"{code}:{field}" for code in CFTC_MARKETS for field in CFTC_FIELDS}
        if set(frame.series) != expected:
            raise ValueError("Missing configured CFTC market/field")
        return frame


class USDAWASDE:
    """Point-in-time WASDE releases supplied from original, locally downloaded CSVs."""

    name = "usda-wasde"

    def __init__(self, files: list[Path]):
        if not files:
            raise ValueError("Supply one or more original USDA WASDE CSV files")
        if any(not path.is_file() or path.suffix.lower() != ".csv" for path in files):
            raise ValueError("USDA WASDE inputs must be existing CSV files")
        self.files = files

    def fetch(self) -> Download:
        # The USDA web server blocked unattended retrieval here. Archive original
        # browser downloads so they remain reproducible without pretending they
        # came from a live API call.
        return Download(
            archive({path.name: path.read_bytes() for path in self.files}),
            "local://user-supplied-usda-wasde-csv",
            "zip",
        )

    def parse(self, raw: bytes) -> pd.DataFrame:
        records = []
        dimensions = []
        release_dates: set[str] = set()
        self.missing_values: list[dict[str, str]] = []
        with ZipFile(BytesIO(raw)) as z:
            for name in sorted(z.namelist()):
                table = pd.read_csv(BytesIO(z.read(name)))
                if set(table.columns) != WASDE_REQUIRED_COLUMNS:
                    raise ValueError("Unexpected USDA WASDE CSV schema")
                if table.empty:
                    raise ValueError("USDA WASDE file is empty")
                release_date = pd.to_datetime(table["ReleaseDate"], errors="raise")
                if release_date.nunique() != 1:
                    raise ValueError("USDA WASDE file contains multiple release dates")
                release = release_date.iloc[0].date().isoformat()
                if release in release_dates:
                    raise ValueError("Duplicate USDA WASDE release supplied")
                release_dates.add(release)
                for data in table.to_dict(orient="records"):
                    if pd.isna(data["Value"]):
                        # Preserve the original row in the raw source. A null value
                        # cannot enter the normalized numeric observation table.
                        self.missing_values.append(
                            {
                                "release_date": release,
                                "commodity": str(data["Commodity"]),
                                "region": str(data["Region"]),
                                "attribute": str(data["Attribute"]),
                            }
                        )
                        continue
                    # A WASDE release contains multiple measures with the same
                    # commodity/region/attribute, particularly reliability tables.
                    # Every published dimension that distinguishes a numeric row
                    # therefore belongs in the normalized series identity.
                    series = (
                        "WASDE|{title}|{reliability}|{commodity}|{region}|{market_year}|"
                        "{attribute}|{period}|{flag}|{unit}"
                    ).format(
                        title=data["ReportTitle"],
                        reliability=data["ReliabilityProjection"],
                        commodity=data["Commodity"],
                        region=data["Region"],
                        market_year=data["MarketYear"],
                        attribute=data["Attribute"],
                        period=data["AnnualQuarterFlag"],
                        flag=data["ProjEstFlag"],
                        unit=data["Unit"],
                    )
                    records.append(
                        (
                            self.name,
                            series,
                            pd.Timestamp(data["ReleaseDate"]).date(),
                            float(data["Value"]),
                            str(data["Unit"]),
                            "monthly",
                            "wasde_estimate",
                        )
                    )
                    # Retain all report dimensions for later point-in-time work.
                    dimensions.append(json.dumps(data, default=str, sort_keys=True))
        frame = pd.DataFrame(records, columns=COLUMNS)
        if frame.empty:
            raise ValueError("USDA WASDE files contain no numeric observations")
        frame["dimensions"] = dimensions
        return frame


class AGSI:
    name = "agsi"

    def fetch(self) -> Download:
        key = os.environ.get("AGSI_API_KEY")
        if not key:
            raise ValueError("AGSI_API_KEY is required")
        rows: list[dict] = []
        page = 1
        with client() as session:
            while True:
                payload = get(
                    session,
                    AGSI_URL,
                    headers={"x-key": key},
                    params={"type": "eu", "size": "300", "page": str(page), "from": "2020-01-01"},
                ).json()
                if payload.get("error") or not payload.get("data"):
                    raise ValueError("AGSI denied access or returned incomplete data")
                rows.extend(payload["data"])
                if page >= int(payload["last_page"]):
                    break
                page += 1
        return Download(json.dumps(rows).encode(), AGSI_URL + "?type=eu&from=2020-01-01", "json")

    def parse(self, raw: bytes) -> pd.DataFrame:
        fields = {
            "gasInStorage": "TWh",
            "injection": "GWh/day",
            "withdrawal": "GWh/day",
            "workingGasVolume": "TWh",
            "full": "%",
        }
        records = []
        for row in json.loads(raw):
            if str(row["code"]).lower() != "eu":
                raise ValueError("Expected EU aggregate, not nested facilities")
            for field, unit in fields.items():
                records.append(
                    (
                        self.name,
                        f"EU:{field}",
                        pd.Timestamp(row["gasDayStart"]).date(),
                        float(str(row[field]).replace(",", "")),
                        unit,
                        "daily",
                        "storage",
                    )
                )
        return pd.DataFrame(records, columns=COLUMNS)


class YahooFutures:
    """Current dated WTI contracts with openly published first-notice metadata.

    Yahoo's uncredentialed chart response supplies daily *closing* prices, not
    exchange settlement prices.  The distinction is explicit in ``dimensions``
    so these observations can validate the mechanics of a contract roll without
    being represented as official settlement data.
    """

    name = "yahoo-futures"
    root_slug = "nymex-cl"

    @staticmethod
    def _yahoo_symbol(symbol: str, event_date: str) -> str:
        # Futures Clock uses a one-digit delivery year (CLX6); Yahoo uses CLX26.
        # Its event date establishes the relevant decade without guessing.
        year = int(event_date[:4])
        if not symbol or not symbol[-1].isdigit():
            raise ValueError("Unexpected Futures Clock WTI contract symbol")
        return symbol[:-1] + str(year % 100).zfill(2) + ".NYM"

    def fetch(self) -> Download:
        with client() as session:
            session.headers["User-Agent"] = "commodity-data-platform/0.2 (+local research pipeline)"
            expiry_response = get(session, FUTURES_CLOCK_EXPIRIES_URL)
            expiry = expiry_response.json()
            events = [
                row
                for row in expiry.get("events", [])
                if row.get("slug") == self.root_slug
                and row.get("kind") in {"ltd", "fnd"}
                and row.get("date")
            ]
            if not events:
                raise ValueError("Futures Clock has no current WTI expiry events")
            by_contract: dict[str, list[dict]] = {}
            for event in events:
                by_contract.setdefault(str(event["symbol"]), []).append(event)
            # The free endpoint aggressively rate-limits burst requests. One
            # near contract per run creates a complete local history over time;
            # each contract keeps the paired FND/LTD metadata needed to test a
            # roll. The next contract is selected after the current one passes.
            candidates = [
                (min(str(e["date"]) for e in contract_events), symbol, contract_events)
                for symbol, contract_events in by_contract.items()
                if any(e.get("kind") == "fnd" for e in contract_events)
            ]
            if not candidates:
                raise ValueError("Futures Clock WTI events lack first-notice dates")
            _, selected_symbol, selected_events = min(candidates)
            by_contract = {selected_symbol: selected_events}
            files = {"futures-clock-expiries.json": expiry_response.content}
            start = int(pd.Timestamp(datetime.now(UTC).date().replace(month=1, day=1)).timestamp())
            end = int(pd.Timestamp(datetime.now(UTC).date()).timestamp()) + 86_400
            for symbol, contract_events in by_contract.items():
                yahoo = self._yahoo_symbol(symbol, str(contract_events[0]["date"]))
                response = get(
                    session,
                    f"{YAHOO_CHART_URL}/{yahoo}",
                    params={"period1": str(start), "period2": str(end), "interval": "1d"},
                )
                files[f"{symbol}.json"] = response.content
        return Download(
            archive(files),
            FUTURES_CLOCK_EXPIRIES_URL + " + Yahoo Finance chart API (dated NYMEX WTI contracts)",
            "zip",
        )

    def parse(self, raw: bytes) -> pd.DataFrame:
        records = []
        with ZipFile(BytesIO(raw)) as z:
            expiry = json.loads(z.read("futures-clock-expiries.json"))
            downloaded_contracts = {
                name.removesuffix(".json")
                for name in z.namelist()
                if name != "futures-clock-expiries.json" and name.endswith(".json")
            }
            events = [
                row
                for row in expiry["events"]
                if row.get("slug") == self.root_slug
                and row.get("symbol") in downloaded_contracts
                and row.get("kind") in {"ltd", "fnd"}
            ]
            metadata: dict[str, dict[str, str]] = {}
            for event in events:
                if not event.get("date"):
                    continue
                contract = metadata.setdefault(str(event["symbol"]), {})
                contract[str(event["kind"])] = str(event["date"])
                contract["expiry_evidence"] = str(event.get("evidence", {}).get("state", "unknown"))
                contract["expiry_source"] = str(event.get("sourceUrl", ""))
            if not metadata:
                raise ValueError("Futures Clock WTI metadata missing")
            for contract_symbol, details in metadata.items():
                if "ltd" not in details or "fnd" not in details:
                    raise ValueError("WTI contract missing last-trade or first-notice date")
                payload = json.loads(z.read(f"{contract_symbol}.json"))
                chart = payload.get("chart", {})
                result = chart.get("result")
                if chart.get("error") or not result or len(result) != 1:
                    raise ValueError("Yahoo dated WTI response missing chart data")
                result0 = result[0]
                timestamps = result0.get("timestamp", [])
                quotes = result0.get("indicators", {}).get("quote", [{}])
                closes = quotes[0].get("close", []) if quotes else []
                volumes = quotes[0].get("volume", []) if quotes else []
                if len(timestamps) != len(closes) or len(timestamps) != len(volumes):
                    raise ValueError("Yahoo dated WTI response has inconsistent arrays")
                dimensions = json.dumps(
                    {
                        "exchange": "NYMEX",
                        "contract": contract_symbol,
                        "yahoo_symbol": result0.get("meta", {}).get("symbol"),
                        "price_field": "close_not_official_settlement",
                        "first_notice_date": details["fnd"],
                        "last_trade_date": details["ltd"],
                        "expiry_evidence": details["expiry_evidence"],
                        "expiry_source": details["expiry_source"],
                    },
                    sort_keys=True,
                )
                for timestamp, close, volume in zip(timestamps, closes, volumes, strict=True):
                    if close is None or volume is None:
                        continue
                    records.append(
                        (
                            self.name,
                            f"NYMEX:{contract_symbol}",
                            pd.Timestamp(timestamp, unit="s", tz="UTC").date(),
                            float(close),
                            "USD/bbl",
                            "daily",
                            "futures_contract_close",
                            dimensions,
                        )
                    )
        frame = pd.DataFrame(records, columns=[*COLUMNS, "dimensions"])
        if frame.empty:
            raise ValueError("Yahoo returned no dated WTI closing prices")
        return frame
