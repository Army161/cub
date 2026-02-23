# Contributing

## Setup

1. Install Python 3.11+ and `uv`
2. Clone the repository
3. Install dependencies:

```bash
make setup
```

4. Copy `.env.example` to `.env` and fill in your values.

## Run Locally

```bash
make run
```

## Tests and Lint

```bash
make test
make lint
```

## Development Notes

- Keep PRs focused and small.
- Add tests for behavior changes.
- Prefer explicit, typed code over magic.
- Keep dependencies minimal.
