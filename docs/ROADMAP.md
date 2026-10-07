# Building the portfolio one project at a time

The screenshots are the target scope, not proof that every suggested data feed
contains the required history. We will release small verified pieces, document
what is real versus synthetic, and only make research claims supported by the data.
The original October 2025 starting date is past; work starts in October 2026.
At eight hours per week, use the milestones below rather than promise dates before
source access is verified.

## Project 1 — shared data platform (current, release 0.2)

Seven public adapters now work: World Bank, EIA public spreadsheets, Westmetall,
CFTC, AGSI+, locally supplied USDA WASDE releases, and a dated NYMEX WTI close
series with Futures Clock first-notice/last-trade metadata.
The platform versions raw/Parquet snapshots, compares revisions, rejects lost
history, reports quality alerts and derives 14 date-aligned series with lineage.
The roll engine supports calendar/business timing and first-notice constraints.
Official settlement history and an exchange calendar remain outstanding.

A searchable catalogue, checksummed backup/restore and two-page note are available.
Daily workflow files exist but are inactive. The initial eight-hours-per-week plan
must account for provider access and operational verification before moving to risk.

See [the detailed completion gates](COMPLETION.md):

1. Official individual-contract settlement history and verified exchange calendar.
2. GitHub activation, off-device backup and verified scheduled/failure recovery runs.

EIA NYMEX rank prices stop after April 5, 2024; the original assumption that EIA
could supply current futures curves was incorrect. No results from the other
projects should quietly substitute spot or monthly benchmarks for futures holdings.

## Project 2 — risk system

Start with a small, explicit hypothetical futures/spread book and contract metadata.
Implement positions → mark-to-market → scenario P&L → historical VaR/ES. Add filtered
historical simulation, limits, historical/hypothetical stresses and backtesting.
Only add options when quotes/volatilities and model assumptions are supported.
Black-76 needs positive forwards/strikes; it cannot model negative WTI forwards
without a different model or an explicitly delimited scenario treatment.

Acceptance: hand-checkable P&L, no look-ahead in rolling risk estimates, correct loss
sign conventions, independently checked quantiles/ES, risk exceptions and a one-page
report. Liquidity/margin estimates require real volume, open interest and margin
assumptions; do not invent them. Then add PDF/dashboard and the research note.

## Project 3 — systematic research

Use point-in-time availability, real contract holdings and trading costs. Add carry,
time-series momentum, cross-sectional momentum and correctly lagged CFTC signals.
Separate signal discovery from evaluation. Include volatility targeting, walk-forward
tests, parameter sensitivity, subperiods, trial counts and deflated Sharpe analysis.

Acceptance: reproducible out-of-sample results and reconciled cash/contract P&L.
Small-universe results demonstrate methodology; they are not proof of deployability.

## Project 4 — discretionary monitor

Choose energy, metals or agriculture based on interest and verified data coverage.
Build the appropriate fundamentals monitor and a prospective paper-trade journal.
Allow explicit no-trade decisions. Record thesis, catalyst, invalidation, sizing,
entry assumptions and contemporaneous evidence; include costs and all losing trades.

Git commit timestamps alone are editable and do not prove contemporaneous publication.
Use an append-only journal plus an external publication/audit timestamp if making
track-record claims. Public publishing is a distinct step. Historical trades added
later must be labelled retrospective. Start prospective collection early once the
niche is chosen, even while finishing the risk system.

## Project 5 — options and volatility lab

First verify options-chain access and begin dated snapshots. Retain bid/ask, quote
times, expiries, underlying prices, rates and dividends. SPY and the listed ETF
options require attention to American exercise and dividends: European SVI/pricing
assumptions must be made explicit and justified, not silently applied.

Then build filtering, implied vols, SVI, butterfly/calendar diagnostics, Greeks,
scenario grids and hedge P&L attribution including residuals and costs. Compare
realized/implied volatility only over aligned horizons and available observations.
Commodity-linked ETF options do not directly represent commodity futures options.

Acceptance: surface diagnostics, pricing/Greek invariants, hedge reconciliation,
a reproducible example and a two-page note reporting limitations.

## Shared quality bar

Every project gets src layout, type checks, meaningful numerical tests, locked
versions, reproducible commands, no committed keys/vendor archives, architecture,
real results and clear limitations. Research notes follow verified results. Later
projects consume this platform's schema instead of creating separate download code.
