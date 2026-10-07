import argparse
import json
import os
from pathlib import Path

import duckdb
import pandas as pd

from commodity_data.connectors import EIA, Connector, WorldBank
from commodity_data.curves import continuous
from commodity_data.derived import Derived
from commodity_data.operations import backup, export_catalog, health, restore
from commodity_data.public_sources import AGSI, CFTC, USDAWASDE, EIAPublic, Westmetall, YahooFutures
from commodity_data.storage import ingest, rebuild

SOURCES: dict[str, type[Connector]] = {
    "worldbank": WorldBank,
    "eia": EIA,
    "eia-public": EIAPublic,
    "westmetall": Westmetall,
    "cftc": CFTC,
    "agsi": AGSI,
    "usda-wasde": USDAWASDE,
    "yahoo-futures": YahooFutures,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Commodity research data platform")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("ingest")
    refresh.add_argument("source", choices=list(SOURCES))
    refresh.add_argument(
        "--files", type=Path, nargs="+", help="Original local CSV files; required for usda-wasde"
    )
    refresh.add_argument("--strict", action="store_true", help="Nonzero exit on quality alerts")
    commands.add_parser("catalog")
    commands.add_parser("health")
    commands.add_parser("derive")
    commands.add_parser("refresh")
    export = commands.add_parser("export-catalog")
    export.add_argument("output", type=Path)
    archive = commands.add_parser("backup")
    archive.add_argument("destination", type=Path)
    recover = commands.add_parser("restore")
    recover.add_argument("archive", type=Path)
    query = commands.add_parser("query")
    query.add_argument("sql")
    curve = commands.add_parser("continuous")
    curve.add_argument("csv", type=Path)
    curve.add_argument("--roll-days", type=int, default=5)
    curve.add_argument("--basis", choices=["calendar", "business"], default="calendar")
    curve.add_argument("--adjustment", choices=["additive", "none"], default="additive")
    curve.add_argument("--holidays", type=Path, help="Text file: one YYYY-MM-DD closure per line")
    args = parser.parse_args()
    if args.command == "health":
        print(json.dumps(health(args.data_dir), indent=2))
        return
    if args.command == "export-catalog":
        export_catalog(args.data_dir, args.output)
        print(args.output)
        return
    if args.command == "backup":
        backup(args.data_dir, args.destination)
        print(args.destination)
        return
    if args.command == "restore":
        restore(args.archive, args.data_dir)
        print(args.data_dir)
        return
    if args.command == "derive":
        report = ingest(Derived(args.data_dir), args.data_dir)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["status"] == "ok" else 1)
    if args.command == "refresh":
        names = ["worldbank", "eia-public", "westmetall", "cftc", "yahoo-futures"]
        if os.environ.get("AGSI_API_KEY"):
            names.append("agsi")
        reports = [ingest(SOURCES[name](), args.data_dir) for name in names]
        reports.append(ingest(Derived(args.data_dir), args.data_dir))
        summary = health(args.data_dir)
        (args.data_dir / "health.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        if os.environ.get("GITHUB_ACTIONS") == "true":
            for report in reports:
                count = len(report.get("new_alerts", []))
                if count:
                    print(f"::warning::{report['source']}: {count} new review alerts")
        raise SystemExit(1 if any(r["status"] != "ok" for r in reports) else 0)
    if args.command == "ingest":
        connector: Connector
        if args.source == "usda-wasde":
            connector = USDAWASDE(args.files or [])
        else:
            if args.files:
                parser.error("--files is only valid with usda-wasde")
            connector = SOURCES[args.source]()
        result = ingest(connector, args.data_dir)
        print(json.dumps(result, indent=2))
        if result["status"] != "ok":
            raise SystemExit(1)
        if result["alerts"] and os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning::{len(result['alerts'])} data-quality alerts; see run report")
        if args.strict and result["alerts"]:
            raise SystemExit(2)
    elif args.command == "continuous":
        print(
            continuous(
                pd.read_csv(args.csv),
                args.roll_days,
                basis=args.basis,
                adjustment=args.adjustment,
                holidays=args.holidays.read_text().splitlines() if args.holidays else None,
            ).to_csv(index=False),
            end="",
        )
    else:
        rebuild(args.data_dir)
        if not (args.data_dir / "catalog.duckdb").exists():
            parser.error("No observations yet. Run ingest worldbank first.")
        with duckdb.connect(str(args.data_dir / "catalog.duckdb"), read_only=True) as con:
            # This is a trusted local analyst CLI, not an untrusted SQL web service.
            sql = (
                "SELECT * FROM catalog ORDER BY source, series"
                if args.command == "catalog"
                else args.sql
            )
            print(con.execute(sql).fetchdf().to_string(index=False))
