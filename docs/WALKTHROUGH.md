# Research walkthrough

[Overview](../README.md) · [Engineering reference](REFERENCE.md)

Follow a source observation through storage, validation and a research query.

## 1. Follow one observation

Run `uv run commodity-data ingest worldbank`. The connector downloads the workbook.
Each price becomes a row: for example source=worldbank, series=Copper,
date=month-end, value=the workbook number, unit=the workbook unit,
frequency=monthly and kind=benchmark. The pipeline adds retrieval time, a run ID
and the SHA-256 of its source bytes. These fields let you trace a number to a file.

The parser skips missing workbook observations. It does not turn missing prices
into zero or carry the previous month forward. Tests use a miniature invented
workbook, so test runs do not depend on the network.

## 2. Inspect coverage before analysis

Run `uv run commodity-data catalog`. Compare first/last dates across series.
Different start dates are real coverage constraints. Open the latest JSON in
`data/runs/` to read alerts. A discontinued commodity is not a pipeline failure,
but it must not silently enter a current risk or signal calculation as fresh data.

Try:

```sh
uv run commodity-data query "SELECT series, last_date FROM catalog ORDER BY last_date LIMIT 10"
uv run commodity-data query "SELECT date, value, unit FROM observations WHERE series = 'Crude oil, WTI' AND date BETWEEN DATE '2020-01-01' AND DATE '2020-06-30' ORDER BY date"
```

That second query shows monthly benchmark prices. It cannot reproduce an individual
futures contract's negative settlement on one day in April 2020. Matching the
instrument and frequency to the question is part of the engineering work.

## 3. Inspect what a second refresh changes

Run ingestion again. `observations` still contains one current row per source,
series and observation date. `vintages` now contains both retrieval snapshots.
If the provider revises history, the older snapshot remains available. We cannot
claim what the provider published in 2020 from a first download made in 2026.

## 4. Understand the roll demonstration

Run `make demo`. The input is explicitly synthetic. On January 14 the held contract
F settles at 70. On January 15 F settles at 71 and G at 76. We earn a price change
of 1 in F, close F, and enter G at 76. On January 16 G settles at 77: another 1.
The roll gap is 5, but it is not earned P&L. Multipliers and costs come later.

The adjusted history is 75, 76, 77. Adjustment is useful for continuous price
charts; future rolls revise previous levels. Actual holdings and settlement changes
are the foundation for the risk engine and backtester.

## 5. Read the implementation in this order

1. `connectors.py`: external formats become common observations.
2. `quality.py`: structural validity versus alerts requiring judgement.
3. `storage.py`: immutable snapshots and latest/vintage catalogue views.
4. `curves.py`: explicit numerical definitions and roll accounting.
5. `cli.py`: commands connecting the modules.
6. `tests/test_platform.py`: numerical examples and failure recovery expectations.

Run `make check` after changes. The next substantive milestone is verified daily
energy coverage and source-specific monitoring, followed by real futures data.

## 6. Explore release 0.2

Run `uv run commodity-data refresh` for configured network sources plus derived series.
`commodity-data health` distinguishes connected sources from the remaining gates.
`commodity-data export-catalog output/catalog.html` creates a searchable local page.
Try `commodity-data query "SELECT * FROM catalog WHERE source = 'derived'"`.

Read `docs/COMPLETION.md` before treating the platform as complete. EIA public XLS
files remove the API-key dependency for the default energy adapter. AGSI has now
been live-verified. USDA WASDE works from original browser-downloaded CSVs; import
future releases with `commodity-data ingest usda-wasde --files ...`. Current
official settlement history and real-roll validation remain unresolved. The example roll demonstration
is still synthetic.
