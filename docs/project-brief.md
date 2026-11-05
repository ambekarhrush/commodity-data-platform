# Commodity Data Platform

*Versioned research data platform · Prepared 5 November 2026*

## The research question

Can heterogeneous commodity observations be made traceable, comparable and reproducible?

## Approach

Source adapters archive inputs and retrieval hashes, validate units and structure, preserve retrieval vintages, and publish DuckDB/Parquet queries and a searchable catalogue. Derived series retain input lineage; contract roll accounting is distinct from spot and rank proxies.

## Evidence and result

The 7 October 2026 local snapshot records 224,844 source observations and 37,747 derived observations across 14 derived series. These are coverage counts, not a common aligned investable universe. The local suite contains 36 tests.

## Scope and limitations

One dated WTI contract close does not validate real roll transitions or official settlements. USDA history is partial and imported manually. Hosted recovery, off-device durability and exchange-session validation need their own evidence. The latest reviewed hosted ingestion job failed during source refresh; the local test suite is not proof of daily operation.

## Explore the project

Follow the README quick start and open the generated catalogue. Inspect docs/COMPLETION.md before discussing operational status; run the existing local test suite.

## Sources and evidence

[docs/COMPLETION.md](../docs/COMPLETION.md) · [docs/RUN_STATUS.md](../docs/RUN_STATUS.md) · [docs/REFERENCE.md](../docs/REFERENCE.md)

---

Hrush Ambekar · Research snapshot reviewed 5 November 2026. See linked source files for full methodology, figures and reproducibility.
