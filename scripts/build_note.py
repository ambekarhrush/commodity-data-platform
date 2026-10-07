"""Reproduce the two-page engineering note from the current local catalogue."""

from datetime import UTC, datetime
from pathlib import Path

import duckdb
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf/project-1-engineering-note.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)
with duckdb.connect(str(ROOT / "data/catalog.duckdb"), read_only=True) as con:
    coverage = con.sql(
        "SELECT source, count(*) AS rows, count(DISTINCT series) AS series "
        "FROM observations GROUP BY source ORDER BY source"
    ).fetchall()
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="TitleCustom",
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=29,
        textColor=colors.HexColor("#173847"),
        spaceAfter=12,
    )
)
styles.add(
    ParagraphStyle(
        name="SubCustom",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#276d74"),
        spaceBefore=13,
        spaceAfter=6,
    )
)
styles.add(
    ParagraphStyle(
        name="BodyCustom",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#233746"),
        spaceAfter=8,
    )
)
styles.add(
    ParagraphStyle(
        name="SmallCustom",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#526674"),
        spaceAfter=5,
    )
)
story = []


def para(text, style="BodyCustom"):
    story.append(Paragraph(text, styles[style]))


para("PROJECT 01 / ENGINEERING RESEARCH NOTE", "SmallCustom")
para("A traceable commodity<br/>data foundation", "TitleCustom")
para(
    "Local release 0.2 | "
    + datetime.now(UTC).strftime("%d %B %Y")
    + " | Completion gates remain open",
    "SmallCustom",
)
para(
    "The platform now ingests six public sources into immutable Parquet snapshots and queries "
    "them through DuckDB. Current data contain <b>"
    + f"{sum(r[1] for r in coverage):,}"
    + "</b> observations "
    "across <b>" + str(sum(r[2] for r in coverage)) + "</b> series, including 14 derived series. "
    "This is a tested research-data foundation; it is not yet a fully connected, hosted futures platform."
)
para("Coverage verified with live downloads", "SubCustom")
rows = [["Source", "Observations", "Series"]] + [[s, f"{n:,}", str(k)] for s, n, k in coverage]
table = Table(rows, colWidths=[260, 130, 90])
table.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173847")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#eef4f6"), colors.white]),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]
    )
)
story.append(table)
para("Series count by source", "SubCustom")
chart = Drawing(480, 150)
maximum_series = max(count for _, _, count in coverage)
for i, (source, _, count) in enumerate(coverage):
    y = 130 - i * 18
    width = 280 * count / maximum_series
    chart.add(
        String(0, y, source, fontName="Helvetica", fontSize=9, fillColor=colors.HexColor("#233746"))
    )
    chart.add(
        Rect(90, y - 3, width, 11, fillColor=colors.HexColor("#3d8790"), strokeColor=None)
    )
    chart.add(String(100 + width, y, str(count), fontName="Helvetica", fontSize=9))
story.append(chart)
para("Why the data model matters", "SubCustom")
para(
    "Each observation retains its source, series, observation date, units, frequency and economic "
    "type. Each snapshot adds a UTC retrieval time, run ID and source-file hash. Monthly benchmarks, "
    "spot prices, positioning, inventories and futures ranks stay distinct. A retrieval timestamp "
    "does not reconstruct the original historical publication time."
)
para(
    "Source download → raw archive → validation and revision comparison → immutable Parquet → "
    "DuckDB current/vintage views → derived series with input run IDs.",
    "SmallCustom",
)
story.append(PageBreak())
para("RELIABILITY / INTERPRETATION / COMPLETION", "SmallCustom")
para("What is proven, and what remains", "TitleCustom")
para("Validation and recovery", "SubCustom")
para(
    "The test suite covers parsing, pagination, retry behavior, missing credentials, credential "
    "redaction, revision tracking, lost-history rejection, unit changes, alert deduplication, "
    "roll accounting and backup integrity. A local archive was restored into a separate directory "
    "and reproduced all current observations. A repeat public refresh completed without introducing "
    "duplicate current observations. The catalogue search was checked in a browser."
)
para(
    "Structural failures keep the previous good snapshot. Full-history review alerts remain "
    "visible, while new alert evidence is distinguished from previously reported events. "
    "Checks are heuristics, not evidence that every observation is economically correct."
)
para("Derived series and roll accounting", "SubCustom")
para(
    "Six metals provide cash-minus-three-month spreads and relative curve slopes. The indicative "
    "3:2:1 spot crack uses 42 gallons per barrel and aligned dates; its product/crude locations "
    "differ, so it is not an executable refinery margin. A WTI first-minus-second futures-rank "
    "spread is historical only. Derived manifests record input snapshots and method version."
)
para(
    "The roll engine supports calendar/business-day offsets, supplied holiday closures, first-notice "
    "constraints and unadjusted/additive series. On a synthetic roll, the held contract moves "
    "70 to 71 while the next contract costs 76: earned price change is 1, not 6. Back-adjusted "
    "levels are revised by later rolls and must not be treated as investable percentage returns."
)
para("Two completion gates", "SubCustom")
for text in [
    (
        "<b>USDA WASDE:</b> seven original official files were imported, preserving release dates, "
        "marketing years and all report dimensions. Future releases need the same local import until "
        "a permitted automated route is available."
    ),
    (
        "<b>1. Individual futures contracts:</b> obtain current settlement histories, expiry/first-notice metadata "
        "and a verified exchange calendar. EIA futures ranks end on 5 April 2024 and cannot supply this."
    ),
    (
        "<b>2. Operations:</b> push to a GitHub repository, configure secrets, verify a hosted run, set "
        "notifications and maintain an off-device backup. Workflow files exist but are inactive locally."
    ),
]:
    para(text)
para("Sources and reproducibility", "SubCustom")
para(
    "Official sources: worldbank.org/en/research/commodity-markets; eia.gov/dnav/pet; "
    "publicreporting.cftc.gov (72hh-3qpy); westmetall.com/en/markdaten.php. "
    "API reference: gie.eu/transparency-platform/GIE_API_documentation_v006.pdf. "
    "WASDE: usda.gov/historical-wasde-report-data-3.",
    "SmallCustom",
)
para(
    "Run: uv sync --frozen --all-extras; make check; commodity-data refresh; "
    "commodity-data health. Data remain local and ignored by Git. GitHub artifacts have finite "
    "retention; the tested local backup is not an off-device backup.",
    "SmallCustom",
)


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#c8d6dc"))
    canvas.line(48, 42, A4[0] - 48, 42)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#526674"))
    canvas.drawString(
        48, 29, "Commodity Data Platform | Local engineering note | No performance claims"
    )
    canvas.drawRightString(A4[0] - 48, 29, str(doc.page))


SimpleDocTemplate(
    str(OUT), pagesize=A4, rightMargin=48, leftMargin=48, topMargin=40, bottomMargin=53
).build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
