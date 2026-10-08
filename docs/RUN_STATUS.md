# Automated refresh status

This file is updated by the daily GitHub Actions refresh. It contains no raw market data or credentials.

Last successful refresh: `2026-10-08T23:29:54.117638+00:00`

| Source | Status | Rows | New review alerts |
| --- | --- | ---: | ---: |
| worldbank | ok | 50,451 | 43 |
| eia-public | ok | 60,924 | 10 |
| westmetall | ok | 30,766 | 4 |
| cftc | ok | 34,980 | 18 |
| agsi | not_connected | 0 | 0 |
| usda-wasde | not_connected | 0 | 0 |
| yahoo-futures | ok | 193 | 0 |
| derived | ok | 37,759 | 18 |

## Remaining completion gates

- AGSI requires a successful authenticated live run
- USDA WASDE source files have not been ingested
- Official exchange settlement feed still required; live dated WTI closes and FND/LTD metadata are available
- Scheduled GitHub execution and off-device backup not yet verified
