import json
from datetime import date
from io import BytesIO
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from commodity_data.connectors import COLUMNS, EIA, Download, WorldBank
from commodity_data.curves import annualized_slope, calendar_spread, continuous, crack_321
from commodity_data.quality import alerts, validate
from commodity_data.storage import ingest, rebuild


def observations(value=70.0):
    return pd.DataFrame(
        [("fixture", "oil", date(2025, 1, 31), value, "USD/bbl", "monthly", "benchmark")],
        columns=COLUMNS,
    )


class Fixture:
    name = "fixture"

    def __init__(self, value=70.0, fail=False):
        self.value, self.fail = value, fail

    def fetch(self):
        return Download(str(self.value).encode(), "synthetic://fixture", "txt")

    def parse(self, raw):
        if self.fail:
            raise ValueError("bad schema")
        return observations(self.value)


def test_vintages_revisions_and_failure(tmp_path):
    first = ingest(Fixture(), tmp_path)
    second = ingest(Fixture(71), tmp_path)
    failed = ingest(Fixture(fail=True), tmp_path)
    assert first["status"] == second["status"] == "ok"
    assert failed["status"] == "failed"
    with duckdb.connect(str(tmp_path / "catalog.duckdb"), read_only=True) as con:
        assert con.sql("select value from observations").fetchone() == (71.0,)
        assert con.sql("select count(*) from vintages").fetchone() == (2,)
    (tmp_path / "catalog.duckdb").unlink()
    rebuild(tmp_path)
    assert (tmp_path / "catalog.duckdb").exists()
    assert len(list((tmp_path / "runs").glob("*.json"))) == 3


@pytest.mark.parametrize("bad", [np.inf, np.nan])
def test_invalid_values(bad):
    with pytest.raises(ValueError):
        validate(observations(bad))


def test_duplicate_rejected_negative_price_allowed():
    frame = observations(-37)
    validate(frame)
    with pytest.raises(ValueError, match="Duplicate"):
        validate(pd.concat([frame, frame]))


def test_quality_does_not_fill_data():
    frame = pd.concat([observations(), observations(150)], ignore_index=True)
    frame.loc[1, "date"] = date(2025, 3, 31)
    result = alerts(frame, date(2025, 7, 1))
    assert {item["check"] for item in result} == {"stale", "gaps", "outlier"}
    assert len(frame) == 2


def test_worldbank_parser():
    data = pd.DataFrame(
        [
            ["title", None],
            [None, "Crude oil, WTI"],
            [None, "($/bbl)"],
            ["2025M01", 70],
            ["2025M02", "…"],
        ]
    )
    raw = BytesIO()
    data.to_excel(raw, sheet_name="Monthly Prices", index=False, header=False)
    parsed = WorldBank().parse(raw.getvalue())
    assert len(parsed) == 1
    assert parsed.date.iloc[0] == date(2025, 1, 31)
    assert parsed.unit.iloc[0] == "($/bbl)"
    validate(parsed)


def test_eia_parser_and_missing_key(monkeypatch):
    raw = json.dumps(
        [
            {
                "series": "RWTC",
                "period": "2020-04-20",
                "value": "-36.98",
                "units": "Dollars per Barrel",
            }
        ]
    ).encode()
    parsed = EIA().parse(raw)
    assert parsed.value.iloc[0] == -36.98
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="EIA_API_KEY"):
        EIA().fetch()


def curve():
    return pd.DataFrame(
        [
            ("2025-01-14", "F", "2025-01-20", 70),
            ("2025-01-14", "G", "2025-02-20", 75),
            ("2025-01-15", "F", "2025-01-20", 71),
            ("2025-01-15", "G", "2025-02-20", 76),
            ("2025-01-16", "G", "2025-02-20", 77),
        ],
        columns=["date", "contract", "expiry", "settle"],
    )


def test_roll_does_not_create_profit():
    result = continuous(curve())
    assert list(result.contract) == ["F", "G", "G"]
    assert list(result.back_adjusted) == [75, 76, 77]
    assert list(result.held_change.iloc[1:]) == [1, 1]
    assert result.roll_gap.sum() == 5
    assert np.allclose(result.back_adjusted.diff().iloc[1:], result.held_change.iloc[1:])


def test_missing_roll_quote_rejected():
    with pytest.raises(ValueError, match="Missing held"):
        continuous(curve().drop(index=2))


def test_missing_front_does_not_silently_roll():
    with pytest.raises(ValueError, match="Missing scheduled"):
        continuous(curve().drop(index=0))


def test_negative_settlements_roll():
    frame = curve()
    frame["settle"] -= 100
    result = continuous(frame)
    assert list(result.back_adjusted) == [-25, -24, -23]


def test_units_and_slope():
    assert crack_321(70, 2, 2) == pytest.approx(14)
    assert calendar_spread(70, 75) == -5
    assert annualized_slope(70, 75, 90) > 0
    with pytest.raises(ValueError):
        annualized_slope(-1, 5, 90)


def test_reject_bad_snapshot_preserves_previous(tmp_path):
    ingest(Fixture(), tmp_path)
    result = ingest(Fixture(np.inf), tmp_path)
    assert result["status"] == "failed"
    with duckdb.connect(str(tmp_path / "catalog.duckdb")) as con:
        assert con.sql("select value from observations").fetchone() == (70.0,)


def test_fixture_is_explicitly_synthetic():
    assert "SYNTHETIC" in Path("examples/README.md").read_text()


def test_eia_pagination(monkeypatch):
    from commodity_data import connectors

    offsets = []

    class Response:
        status_code = 200

        def __init__(self, offset):
            self.offset = offset

        def json(self):
            return {
                "response": {
                    "total": "2",
                    "data": [
                        {
                            "series": "RWTC",
                            "period": f"2025-01-0{self.offset + 2}",
                            "value": "70",
                            "units": "Dollars per Barrel",
                        }
                    ],
                }
            }

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params):
            offset = int(params["offset"])
            offsets.append(offset)
            return Response(offset)

    monkeypatch.setenv("EIA_API_KEY", "synthetic-secret")
    monkeypatch.setattr(connectors, "client", Session)
    downloaded = EIA().fetch()
    assert offsets == [0, 1]
    assert len(EIA().parse(downloaded.raw)) == 2
    assert "synthetic-secret" not in downloaded.url
    assert b"synthetic-secret" not in downloaded.raw


def test_exception_report_redacts_credentials(tmp_path):
    class FailedSource(Fixture):
        def fetch(self):
            raise RuntimeError("https://example.invalid/?api_key=synthetic-secret")

    result = ingest(FailedSource(), tmp_path)
    assert result["status"] == "failed"
    assert "synthetic-secret" not in json.dumps(result)


def test_roll_across_two_switches():
    frame = pd.DataFrame(
        [
            ("2025-01-14", "F", "2025-01-20", 70),
            ("2025-01-14", "G", "2025-02-20", 75),
            ("2025-01-15", "F", "2025-01-20", 71),
            ("2025-01-15", "G", "2025-02-20", 76),
            ("2025-02-14", "G", "2025-02-20", 80),
            ("2025-02-14", "H", "2025-03-20", 77),
            ("2025-02-15", "G", "2025-02-20", 81),
            ("2025-02-15", "H", "2025-03-20", 78),
        ],
        columns=["date", "contract", "expiry", "settle"],
    )
    result = continuous(frame)
    assert list(result.roll_gap) == [0, 5, 0, -3]
    assert list(result.held_change.iloc[1:]) == [1, 4, 1]
    assert np.allclose(result.back_adjusted.diff().iloc[1:], result.held_change.iloc[1:])
