# Project 1 completion gates — 7 October 2026

The original brief remains the target. Release 0.2 completes much of the local
implementation, but it is not the full hosted, official-settlement live-futures system.

## Verified locally

- World Bank, EIA public downloads, Westmetall, CFTC, AGSI+ and USDA WASDE ingestion.
- 224,844 source observations plus 37,747 derived observations; 13,147 series total.
- Six metals' cash/3M spreads and relative slopes, indicative spot crack, historical
  WTI rank spread; exact-date joins, unit checks and input-snapshot lineage.
- Snapshot revision detection, lost-history/unit-change rejection, file locking,
  bounded retry, archived reports and deduplicated new alert evidence.
- Calendar/business-day rolls, optional first-notice constraint, none/additive
  adjustment, negative-settlement handling and synthetic accounting invariants.
- Searchable HTML catalogue and SQL CLI.
- Checksummed local backup and restore.
- Two-page engineering note, locked dependencies, CI and daily workflow files.
- A live individual NYMEX WTI contract close series, with first-notice and
  last-trade metadata attached to every observation.

## 1. AGSI+ live verification — complete

The EU aggregate adapter completed a live authenticated run: 12,355 daily
observations from 2020 onward. It remains part of `refresh` whenever
`AGSI_API_KEY` is present. Keep the key in an environment variable or GitHub secret.

## 2. USDA history extension

The WASDE adapter now ingests original, browser-downloaded official CSV files and
preserves release date/time and every report dimension. Seven files from March to
September 2026 were validated and loaded. The USDA site still blocks unattended
download from this machine, so subsequent releases should be downloaded normally
and ingested through the local command until a permitted programmatic route exists.

Download the remaining historical monthly files from April 2010 onward. The adapter
already distinguishes report release date, commodity, region, marketing year,
balance-sheet attribute, projection flags, units and reliability measures. Add a
source-discovery process or permitted stable download route later.
Do not flatten multiple marketing years into duplicate commodity/date rows or
pretend forecast marketing years are future observation dates.

Source checked: https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-2026-09.csv

## 3. Real individual-contract futures and exchange metadata

EIA's rank series stop after 5 April 2024. The platform now imports the current
dated NYMEX WTI contract available from Yahoo Finance, paired with versioned,
open Futures Clock first-notice/last-trade metadata. The initial import is
`NYMEX:CLX6`, with 192 daily closes from 2 January to 7 October 2026. This is
enough to exercise contract identity and a first-notice-constrained roll rule.

The price is deliberately labelled `close_not_official_settlement`: Yahoo's daily
close is not CME's official settlement. Futures Clock is an open, reviewed
reference for expiry events, not the exchange's official holiday calendar.

Remaining input: an authorized official settlement history plus a verified venue
holiday/session calendar. Preserve date, exchange, market, contract, settlement,
currency, price unit, multiplier, expiry and (where relevant) first-notice date.
Volume/open interest are needed later for liquidity analysis and any volume-based
roll policy.

Then validate venue holiday/session calendars, settlement timing and two or more
real roll transitions. Persist validated contract metadata and real continuous
outputs with lineage. Generic weekday-plus-holiday logic is not itself a verified
exchange calendar.

## 4. Hosted operations and durable backup

Need a target GitHub account/repository. No repository has been created or pushed,
and the machine has no gh executable. The workflow is ready for review locally.

Activation sequence: create/push repository, configure AGSI secret, manually run
CI and refresh, verify artifact restoration, arrange off-device archival, simulate
a failure and verify notification, then verify a scheduled run. Keep raw vendor
data out of Git; review access to artifacts before sharing the repository.

Local ZIP backups work, but they do not protect against loss of this computer.
GitHub artifacts expire, so they are not sufficient as the only year-long archive.

## Remaining hardening once these gates are supplied

Define a monitored research universe and justified retired-series exceptions;
calibrate quality thresholds by source/series; encode actual release calendars;
add provider ID migrations/instrument metadata where the chosen universe needs it.
Source-level health and generic checks already run. Do not call those checks
complete financial data validation.

Completion means all six sources intended for the chosen scope work, real futures
rolls are validated, daily hosted execution and recovery are demonstrated, and
limitations in the catalogue/note are updated to reflect that evidence.
