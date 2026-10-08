# Contributing

## Local setup

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --frozen --extra dev
make check
```

`make check` runs formatting/lint checks, static types and the test suite. Run it
before opening a pull request.

## Source adapters

Each adapter must preserve the original source response in the local raw archive,
parse it into the platform's normalized observation schema, and reject unexpected
source schemas instead of silently guessing. Keep credentials in environment
variables or GitHub Actions secrets; never add keys, `.env` files, raw vendor data,
or generated catalogue/backup files to Git.

Be exact about what a value represents. For example, an exchange settlement, a
provider closing price and a continuous futures rank are different series and must
not share a label.

## Tests and review

Add a focused fixture test when a change affects parsing, validation, roll logic or
provenance. Tests must not require network access or credentials. Keep commits small
and describe the observable behaviour changed, including source coverage or known
limitations where relevant.

## Pull requests

Include:

- the data or behaviour changed;
- the source and its access/usage constraint;
- validation run locally; and
- any remaining limitation that a reviewer should not mistake for production coverage.
