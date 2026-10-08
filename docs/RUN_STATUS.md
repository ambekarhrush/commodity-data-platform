# Source status

This initial report was generated locally. No hosted daily-ingestion run has been verified.
Successful hosted refreshes will replace this report automatically.

[Workflow history](https://github.com/ambekarhrush/commodity-data-platform/actions/workflows/daily.yml) · [Project overview](../README.md)

Local health report generated: `2026-10-08T12:49:43.390201+00:00`

| Source | Status | Rows | New review alerts |
| --- | --- | ---: | ---: |
| worldbank | ok | 50,451 | 0 |
| eia-public | ok | 60,924 | 0 |
| westmetall | ok | 30,748 | 0 |
| cftc | ok | 34,980 | 0 |
| agsi | ok | 12,355 | 2 |
| usda-wasde | ok | 35,194 | 0 |
| yahoo-futures | ok | 192 | 0 |
| derived | ok | 37,747 | 0 |

## Remaining completion gates

- Official exchange settlement feed still required; live dated WTI closes and FND/LTD metadata are available
- Scheduled GitHub execution and off-device backup not yet verified
