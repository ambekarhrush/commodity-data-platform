# Automated refresh status

This file is updated by the daily GitHub Actions refresh. It contains no raw market data or credentials.

Last successful refresh: `2026-10-07T18:59:34.555145+00:00`

| Source | Status | Rows | New review alerts |
| --- | --- | ---: | ---: |
| worldbank | ok | 50,451 | 0 |
| eia-public | ok | 60,924 | 0 |
| westmetall | ok | 30,748 | 0 |
| cftc | ok | 34,980 | 0 |
| agsi | not_connected | 0 | 0 |
| usda | not_connected | 0 | 0 |
| derived | ok | 37,747 | 0 |

## Remaining completion gates

- AGSI requires a successful authenticated live run
- USDA WASDE download returned HTTP 403; adapter is not implemented
- Live individual-contract settlements and exchange calendar still required
- GitHub remote, scheduled execution and off-device backup not activated
