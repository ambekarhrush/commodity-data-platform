# Automated refresh status

This file is updated by the daily GitHub Actions refresh. It contains no raw market data or credentials.

Last successful refresh: `2026-10-10T21:55:24.275076+00:00`

| Source | Status | Rows | New review alerts |
| --- | --- | ---: | ---: |
| worldbank | ok | 50,451 | 0 |
| eia-public | ok | 60,924 | 0 |
| westmetall | ok | 30,802 | 0 |
| cftc | ok | 35,013 | 0 |
| agsi | not_connected | 0 | 0 |
| usda-wasde | not_connected | 0 | 0 |
| yahoo-futures | ok | 194 | 0 |
| derived | ok | 37,783 | 4 |

## Remaining completion gates

- AGSI requires a successful authenticated live run
- USDA WASDE source files have not been ingested
- Official exchange settlement feed still required; live dated WTI closes and FND/LTD metadata are available
- Scheduled GitHub execution and off-device backup not yet verified
