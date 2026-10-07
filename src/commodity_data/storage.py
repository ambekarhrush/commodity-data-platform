"""Immutable Parquet snapshots with atomically switched DuckDB views."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd
from filelock import FileLock

from commodity_data.changes import compare
from commodity_data.connectors import Connector
from commodity_data.quality import alerts, validate


def literal(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def rebuild(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".writer.lock"), timeout=30):
        _rebuild(root)


def _rebuild(root: Path) -> None:
    # Relative data directory can be restored anywhere; regenerate absolute view paths.
    manifests = sorted((root / "runs").glob("*.json"))
    latest: dict[str, str] = {}
    paths = []
    for manifest in manifests:
        run = json.loads(manifest.read_text())
        if run["status"] == "ok":
            relative = Path(run["parquet"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "parquet":
                raise ValueError("Unsafe snapshot path in manifest")
            if not (root / relative).is_file():
                raise ValueError("Missing snapshot referenced by manifest")
            latest[run["source"]] = run["parquet"]
            paths.append(run["parquet"])
    if not paths:
        return

    def scan(items: list[str]) -> str:
        return (
            "read_parquet([" + ",".join(literal(root / p) for p in items) + "], union_by_name=true)"
        )

    with duckdb.connect(str(root / "catalog.duckdb")) as con:
        con.execute("BEGIN")
        con.execute(
            "CREATE OR REPLACE VIEW observations AS SELECT * FROM " + scan(list(latest.values()))
        )
        con.execute("CREATE OR REPLACE VIEW vintages AS SELECT * FROM " + scan(paths))
        con.execute("""CREATE OR REPLACE VIEW catalog AS
            SELECT source, series, unit, frequency, kind, min(date) AS first_date,
                   max(date) AS last_date, count(*) AS observations
            FROM observations GROUP BY ALL""")
        con.execute("COMMIT")


def ingest(connector: Connector, root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".writer.lock"), timeout=30):
        return _ingest(connector, root)


def _ingest(connector: Connector, root: Path) -> dict:
    stamp = datetime.now(UTC)
    run_id = stamp.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    for directory in ["raw", "parquet", "runs"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    report: dict = {
        "run_id": run_id,
        "source": connector.name,
        "retrieved_at": stamp.isoformat(),
        "status": "failed",
    }
    manifest = root / "runs" / f"{run_id}.json"
    previous = None
    previous_report: dict = {}
    for old_path in sorted((root / "runs").glob("*.json"), reverse=True):
        old_report = json.loads(old_path.read_text())
        if old_report["source"] == connector.name and old_report["status"] == "ok":
            previous = pd.read_parquet(root / old_report["parquet"])
            previous_report = old_report
            break
    try:
        download = connector.fetch()
        digest = hashlib.sha256(download.raw).hexdigest()
        raw_path = root / "raw" / f"{digest}.{download.extension}"
        if not raw_path.exists():
            raw_temp = raw_path.with_suffix(".tmp")
            raw_temp.write_bytes(download.raw)
            raw_temp.replace(raw_path)
        report.update(url=download.url, sha256=digest, raw=str(raw_path.relative_to(root)))
        frame = connector.parse(download.raw)
        validate(frame)
        if set(frame.source) != {connector.name}:
            raise ValueError("Connector source mismatch")
        if hasattr(connector, "lineage"):
            report["lineage"] = connector.lineage
            report["method_version"] = "derived-v1"
        if hasattr(connector, "missing_values"):
            missing_values = connector.missing_values
            report["source_missing_values"] = {
                "count": len(missing_values),
                "sample": missing_values[:50],
            }
        report["changes"] = compare(previous, frame)
        report["alerts"] = alerts(frame, stamp.date())
        old_signatures = {
            (a["series"], a["check"], a.get("evidence", ""))
            for a in previous_report.get("alerts", [])
        }
        report["new_alerts"] = [
            a
            for a in report["alerts"]
            if (a["series"], a["check"], a.get("evidence", "")) not in old_signatures
        ]
        frame["retrieved_at"] = stamp
        frame["run_id"] = run_id
        frame["source_sha256"] = digest
        parquet = root / "parquet" / f"{run_id}.parquet"
        parquet_temp = parquet.with_suffix(".tmp")
        frame.to_parquet(parquet_temp, index=False)
        parquet_temp.replace(parquet)
        report.update(status="ok", rows=len(frame), parquet=str(parquet.relative_to(root)))
    except Exception as exc:  # noqa: BLE001 - record failures without leaking credentials
        # Exception messages from HTTP libraries may contain API keys.
        report["error_type"] = type(exc).__name__
        report["message"] = "Ingestion failed; previous successful snapshot remains available."
    temp = manifest.with_suffix(".tmp")
    temp.write_text(json.dumps(report, indent=2))
    temp.replace(manifest)
    try:
        _rebuild(root)
    except Exception:
        report["catalog_error"] = "Saved source run; catalogue rebuild failed. Retry catalog."
        manifest.write_text(json.dumps(report, indent=2))
        raise
    return report
