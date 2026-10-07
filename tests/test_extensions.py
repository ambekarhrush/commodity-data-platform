import json
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import duckdb
import httpx
import pandas as pd
import pytest

from commodity_data.changes import compare
from commodity_data.connectors import COLUMNS, Download
from commodity_data.curves import continuous
from commodity_data.derived import Derived
from commodity_data.operations import backup, health, restore
from commodity_data.public_sources import (
    AGSI,
    CFTC,
    CFTC_FIELDS,
    CFTC_MARKETS,
    EIA_FILES,
    USDAWASDE,
    EIAPublic,
    Westmetall,
    YahooFutures,
    archive,
)
from commodity_data.storage import ingest
from commodity_data.transport import get


def frame(value=70):
    return pd.DataFrame(
        [("fixture", "oil", date(2025, 1, 31), value, "USD/bbl", "monthly", "spot")],
        columns=COLUMNS,
    )


class Fixture:
    name = "fixture"

    def fetch(self):
        return Download(b"synthetic", "synthetic://test", "txt")

    def parse(self, raw):
        return frame()


def test_dropped_history_and_unit_change_rejected():
    old = pd.concat([frame(), frame()], ignore_index=True)
    old.loc[1, "date"] = date(2025, 2, 28)
    with pytest.raises(ValueError, match="lost"):
        compare(old, frame())
    new = frame()
    new["unit"] = "USD/gal"
    with pytest.raises(ValueError, match="metadata"):
        compare(frame(), new)


def test_revision_report():
    result = compare(frame(), frame(71))
    assert result["revised"] == 1
    assert result["revision_sample"][0]["value_old"] == 70
    assert result["revision_sample"][0]["date"] == "2025-01-31"


def test_alerts_deduplicated_across_runs(tmp_path):
    a = ingest(Fixture(), tmp_path)
    b = ingest(Fixture(), tmp_path)
    assert len(a["new_alerts"]) == 1
    assert len(b["alerts"]) == 1 and b["new_alerts"] == []


def test_archive_restore_and_no_overwrite(tmp_path):
    root = tmp_path / "data"
    ingest(Fixture(), root)
    target = tmp_path / "backup.zip"
    backup(root, target)
    restored = tmp_path / "restored"
    restore(target, restored)
    with duckdb.connect(str(restored / "catalog.duckdb")) as con:
        assert con.sql("select value from observations").fetchone() == (70,)
    with pytest.raises(ValueError, match="empty"):
        restore(target, restored)


def test_backup_corruption_rejected_before_writing(tmp_path):
    target = tmp_path / "bad.zip"
    with ZipFile(target, "w") as z:
        z.writestr("checksums.json", json.dumps({"raw/test.txt": "bad-hash"}))
        z.writestr("raw/test.txt", "modified")
    with pytest.raises(ValueError, match="checksum"):
        restore(target, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_archive_path_traversal_rejected(tmp_path):
    target = tmp_path / "bad.zip"
    with ZipFile(target, "w") as z:
        z.writestr("checksums.json", json.dumps({"../escape": "hash"}))
        z.writestr("../escape", "payload")
    with pytest.raises(ValueError, match="Unsafe"):
        restore(target, tmp_path / "restored")


def test_eia_workbooks_and_source_key_check():
    files = {}
    for series in EIA_FILES:
        table = pd.DataFrame(
            [
                ["Contents", "Title"],
                ["Sourcekey", series],
                ["Date", "Value"],
                [pd.Timestamp("2025-01-03"), 71],
            ]
        )
        raw = BytesIO()
        table.to_excel(raw, sheet_name="Data 1", index=False, header=False)
        files[series + ".xls"] = raw.getvalue()
    result = EIAPublic().parse(archive(files))
    assert len(result) == 8
    assert result[result.series == "WCESTUS1"].frequency.iloc[0] == "weekly"
    assert result[result.series == "RCLC1"].kind.iloc[0] == "futures_rank_discontinued"
    files["RWTC.xls"] = files["RBRTE.xls"]
    with pytest.raises(ValueError, match="source key"):
        EIAPublic().parse(archive(files))


def test_westmetall_units_dates_and_missing():
    raw = archive(
        {
            "Cu-2025.html": b"<h1>LME Copper Cash-Settlement</h1><table><tr>"
            b"<td>03. January 2025</td><td>9,000.00</td><td>9,050.50</td><td>-</td>"
            b"</tr></table>"
        }
    )
    result = Westmetall().parse(raw)
    assert list(result.value) == [9000, 9050.5]
    assert set(result.unit) == {"USD/tonne"}
    assert result.date.iloc[0] == date(2025, 1, 3)


def test_cftc_all_expected_markets_and_family():
    rows = [
        {
            "cftc_contract_market_code": code,
            "report_date_as_yyyy_mm_dd": "2025-01-07",
            "futonly_or_combined": "FutOnly",
            **dict.fromkeys(CFTC_FIELDS, "100"),
        }
        for code in CFTC_MARKETS
    ]
    assert len(CFTC().parse(json.dumps(rows).encode())) == 33
    rows[0]["futonly_or_combined"] = "Combined"
    with pytest.raises(ValueError, match="futures-only"):
        CFTC().parse(json.dumps(rows).encode())


def test_agsi_units_and_key(monkeypatch):
    row = {
        "code": "eu",
        "gasDayStart": "2025-01-03",
        "gasInStorage": "700",
        "injection": "1,000.5",
        "withdrawal": "2,000",
        "workingGasVolume": "1000",
        "full": "70",
    }
    result = AGSI().parse(json.dumps([row]).encode())
    assert result[result.series == "EU:injection"].value.iloc[0] == 1000.5
    assert result[result.series == "EU:injection"].unit.iloc[0] == "GWh/day"
    monkeypatch.delenv("AGSI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="AGSI_API_KEY"):
        AGSI().fetch()


def test_agsi_pagination(monkeypatch):
    from commodity_data import public_sources

    pages = []

    def respond(request):
        pages.append(request.url.params["page"])
        assert request.headers["x-key"] == "synthetic-key"
        return httpx.Response(200, json={"last_page": 2, "data": [{"code": "eu"}]})

    monkeypatch.setenv("AGSI_API_KEY", "synthetic-key")
    monkeypatch.setattr(
        public_sources, "client", lambda: httpx.Client(transport=httpx.MockTransport(respond))
    )
    download = AGSI().fetch()
    assert pages == ["1", "2"]
    assert len(json.loads(download.raw)) == 2
    assert "synthetic-key" not in download.url


def test_yahoo_futures_parses_dated_contract_and_expiry_metadata():
    expiry = {
        "events": [
            {"slug": "nymex-cl", "symbol": "CLX6", "kind": "ltd", "date": "2026-10-20", "evidence": {"state": "rule_calculated"}, "sourceUrl": "https://example.test/ltd"},
            {"slug": "nymex-cl", "symbol": "CLX6", "kind": "fnd", "date": "2026-10-22", "evidence": {"state": "rule_calculated"}, "sourceUrl": "https://example.test/fnd"},
        ]
    }
    chart = {"chart": {"result": [{"meta": {"symbol": "CLX26.NYM"}, "timestamp": [1791331200], "indicators": {"quote": [{"close": [88.1], "volume": [123]}]}}], "error": None}}
    raw = archive({"futures-clock-expiries.json": json.dumps(expiry).encode(), "CLX6.json": json.dumps(chart).encode()})
    result = YahooFutures().parse(raw)
    assert result.series.iloc[0] == "NYMEX:CLX6"
    assert result.kind.iloc[0] == "futures_contract_close"
    dimensions = json.loads(result.dimensions.iloc[0])
    assert dimensions["first_notice_date"] == "2026-10-22"
    assert dimensions["price_field"] == "close_not_official_settlement"
    assert YahooFutures._yahoo_symbol("CLX6", "2026-10-20") == "CLX26.NYM"


def test_http_retry(monkeypatch):
    statuses = iter([429, 503, 200])
    from commodity_data import transport

    delays = []
    monkeypatch.setattr(transport.time, "sleep", delays.append)
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(next(statuses)))
    ) as client:
        assert get(client, "https://example.invalid").status_code == 200
    assert delays == [1, 2]


def test_derived_alignment_and_units(tmp_path):
    # The derivation expects all six metals if Westmetall is present.
    from commodity_data.public_sources import METALS

    rows = []
    for symbol in METALS:
        for field, value in [("cash", 100), ("3m", 105)]:
            for dt in ["2025-01-02", "2025-01-03"]:
                if field == "3m" and dt == "2025-01-02":
                    continue
                rows.append(
                    {
                        "source": "westmetall",
                        "series": f"LME_{symbol}_{field}",
                        "date": dt,
                        "value": value,
                        "unit": "USD/tonne",
                        "run_id": "input-run",
                    }
                )
    d = Derived(tmp_path)
    result = d.parse(json.dumps(rows).encode())
    assert len(result) == 12
    assert set(result.date) == {date(2025, 1, 3)}
    assert result[result.series == "LME_Cu_cash_minus_3m"].value.iloc[0] == -5
    assert d.lineage == {"westmetall": ["input-run"]}
    rows[0]["unit"] = "USD/bbl"
    with pytest.raises(ValueError, match="units"):
        d.parse(json.dumps(rows).encode())


def test_business_roll_first_notice_and_holiday():
    rows = []
    for dt in ["2025-01-16", "2025-01-17", "2025-01-21"]:
        rows.extend(
            [(dt, "F", "2025-02-01", "2025-01-22", 70), (dt, "G", "2025-03-01", "2025-02-20", 75)]
        )
    quotes = pd.DataFrame(rows, columns=["date", "contract", "expiry", "first_notice", "settle"])
    result = continuous(quotes, 2, basis="business", holidays=["2025-01-20"])
    assert list(result.contract) == ["F", "G", "G"]
    assert result.held_change.iloc[1] == 0
    with pytest.raises(ValueError, match="business session"):
        continuous(quotes, 2, basis="business")


def test_health_discloses_missing_sources(tmp_path):
    result = health(tmp_path)
    assert all(s["status"] == "not_connected" for s in result["sources"])
    assert len(result["completion_blockers"]) == 4


def test_new_outlier_on_same_series_is_not_suppressed(tmp_path):
    class Growing(Fixture):
        def __init__(self, values):
            self.values = values

        def parse(self, raw):
            rows = []
            for index, value in enumerate(self.values):
                f = frame(value)
                f["date"] = date(2025, index + 1, 1)
                rows.append(f)
            return pd.concat(rows, ignore_index=True)

    ingest(Growing([70, 150]), tmp_path)
    second = ingest(Growing([70, 150, 400]), tmp_path)
    assert any(a["check"] == "outlier" for a in second["new_alerts"])


def test_usda_wasde_preserves_release_dimensions(tmp_path):
    source = tmp_path / "wasde.csv"
    pd.DataFrame(
        [
            {
                "WasdeNumber": 675,
                "ReportDate": "September 2026",
                "ReportTitle": "Test report",
                "Attribute": "Ending Stocks",
                "ReliabilityProjection": "",
                "Commodity": "Corn",
                "Region": "United States",
                "MarketYear": "2026/27",
                "ProjEstFlag": "Proj.",
                "AnnualQuarterFlag": "Annual",
                "Value": 1234.0,
                "Unit": "Million Bushels",
                "ReleaseDate": "2026-09-11",
                "ReleaseTime": "12:00:00.0000000",
                "ForecastYear": 2026,
                "ForecastMonth": 9,
            }
        ]
    ).to_csv(source, index=False)
    parsed = USDAWASDE([source]).parse(USDAWASDE([source]).fetch().raw)
    assert parsed.date.iloc[0] == date(2026, 9, 11)
    assert "|Corn|United States|2026/27|Ending Stocks|" in parsed.series.iloc[0]
    assert json.loads(parsed.dimensions.iloc[0])["ReleaseTime"] == "12:00:00.0000000"


def test_usda_rejects_duplicate_release_dates(tmp_path):
    columns = [
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
    ]
    files = []
    for name in ["a.csv", "b.csv"]:
        path = tmp_path / name
        pd.DataFrame(
            [
                [
                    675,
                    "September 2026",
                    "Report",
                    "Ending Stocks",
                    "",
                    "Corn",
                    "US",
                    "2026/27",
                    "Proj.",
                    "Annual",
                    1,
                    "Bushels",
                    "2026-09-11",
                    "12:00",
                    2026,
                    9,
                ]
            ],
            columns=columns,
        ).to_csv(path, index=False)
        files.append(path)
    with pytest.raises(ValueError, match="Duplicate"):
        USDAWASDE(files).parse(USDAWASDE(files).fetch().raw)
