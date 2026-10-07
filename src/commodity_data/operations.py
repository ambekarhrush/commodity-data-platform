"""Health reports, a portable catalogue, and verified archive/restore operations."""

import hashlib
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import duckdb
from filelock import FileLock

from commodity_data.storage import rebuild


def health(root: Path) -> dict:
    latest: dict[str, dict] = {}
    good: dict[str, dict] = {}
    for path in sorted((root / "runs").glob("*.json")):
        run = json.loads(path.read_text())
        latest[run["source"]] = run
        if run["status"] == "ok":
            good[run["source"]] = run
    sources = []
    now = datetime.now(UTC)
    for name in [
        "worldbank", "eia-public", "westmetall", "cftc", "agsi", "usda-wasde", "yahoo-futures", "derived"
    ]:
        last = latest.get(name, {})
        success = good.get(name, {})
        retrieved = success.get("retrieved_at")
        overdue = bool(
            retrieved and (now - datetime.fromisoformat(retrieved)).total_seconds() > 36 * 3600
        )
        sources.append(
            {
                "source": name,
                "status": last.get("status", "not_connected"),
                "last_success": retrieved,
                "refresh_overdue": overdue,
                "rows": success.get("rows", 0),
                "alerts": len(last.get("alerts", [])),
                "new_alerts": len(last.get("new_alerts", [])),
                "revised": last.get("changes", {}).get("revised", 0),
            }
        )
    return {
        "generated_at": now.isoformat(),
        "sources": sources,
        "completion_blockers": [
            *(["AGSI requires a successful authenticated live run"] if "agsi" not in good else []),
            *([] if "usda-wasde" in good else ["USDA WASDE source files have not been ingested"]),
            *(
                ["Official exchange settlement feed still required; live dated WTI closes and FND/LTD metadata are available"]
                if "yahoo-futures" in good
                else ["Live individual-contract prices and exchange calendar still required"]
            ),
            "GitHub remote, scheduled execution and off-device backup not activated",
        ],
    }


def export_catalog(root: Path, output: Path) -> None:
    rebuild(root)
    report = health(root)
    with duckdb.connect(str(root / "catalog.duckdb"), read_only=True) as con:
        frame = con.execute("SELECT * FROM catalog ORDER BY source, series").fetchdf()
    cells = []
    for row in frame.itertuples(index=False, name=None):
        cells.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>")
    cards = "".join(
        f"<article><b>{html.escape(s['source'])}</b><p>{s['status']}</p>"
        f"<small>{s['rows']:,} rows · {s['alerts']} review alerts</small></article>"
        for s in report["sources"]
    )
    blockers = "".join(f"<li>{html.escape(b)}</li>" for b in report["completion_blockers"])
    headers = "".join(f"<th>{html.escape(c.replace('_', ' '))}</th>" for c in frame.columns)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Data Catalogue</title><style>
body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f4f6f8;color:#172b3a}
main{max-width:1400px;margin:auto;padding:40px}h1{font-size:38px;margin:4px 0}
.eyebrow{color:#386e76;font-weight:700;letter-spacing:2px;font-size:12px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}article{background:white;
border:1px solid #dce4e9;border-radius:10px;padding:16px;min-width:140px}
article p{margin:5px 0}small{color:#526674}input{padding:12px;width:340px;max-width:85%;
border:1px solid #b4c5cd;border-radius:6px;margin:15px 0}table{border-collapse:collapse;
width:100%;background:white;font-size:13px}th,td{text-align:left;padding:10px;
border-bottom:1px solid #e6ecef}th{background:#173847;color:white;position:sticky;top:0}
.scroll{overflow:auto}aside{border-left:4px solid #c39644;padding:8px 18px;background:#fff8e9}
</style><main><div class="eyebrow">PROJECT 01 / LOCAL RESEARCH DATA</div>
<h1>Commodity data catalogue</h1><p>"""
        + html.escape(report["generated_at"])
        + """
 · Static snapshot. Regenerate after refreshing data.</p><div class="cards">"""
        + cards
        + """
</div><aside><b>Completion gates still open</b><ul>"""
        + blockers
        + """</ul></aside>
<label for="search">Find a source, commodity or unit</label><br><input id="search"
placeholder="Try Copper, weekly or USD/bbl" type="search"><div class="scroll">
<table><thead><tr>"""
        + headers
        + "</tr></thead><tbody>"
        + "".join(cells)
        + """</tbody></table>
</div><p>Monthly benchmarks, spot prices, positioning and historical futures ranks
are distinct datasets. Retrieval timestamps do not establish original publication time.</p>
</main><script>document.querySelector('#search').addEventListener('input', e => {
const q=e.target.value.toLowerCase(); document.querySelectorAll('tbody tr').forEach(
r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script></html>"""
    )


def backup(root: Path, destination: Path) -> None:
    root = root.resolve()
    destination = destination.resolve()
    if destination.is_relative_to(root):
        raise ValueError("Store backups outside the data directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    with FileLock(str(root / ".writer.lock"), timeout=30):
        files = sorted(
            p
            for folder in ["raw", "runs", "parquet"]
            for p in (root / folder).glob("*")
            if p.is_file() and p.suffix != ".tmp"
        )
        if not files:
            raise ValueError("No data to back up")
        hashes = {}
        with ZipFile(temp, "w", ZIP_DEFLATED) as z:
            for path in files:
                raw = path.read_bytes()
                name = path.relative_to(root).as_posix()
                hashes[name] = hashlib.sha256(raw).hexdigest()
                z.writestr(name, raw)
            z.writestr("checksums.json", json.dumps(hashes))
        temp.replace(destination)


def restore(archive: Path, destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Restore destination must be empty; existing data are never overwritten")
    # Validate the complete archive before writing anything. No arbitrary extraction paths.
    with ZipFile(archive) as z:
        hashes = json.loads(z.read("checksums.json"))
        if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(hashes) | {
            "checksums.json"
        }:
            raise ValueError("Archive inventory mismatch")
        for name, digest in hashes.items():
            path = Path(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or path.parts[0] not in {"raw", "runs", "parquet"}
            ):
                raise ValueError("Unsafe archive path")
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                raise ValueError("Backup checksum mismatch")
        for name in hashes:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    rebuild(destination)
