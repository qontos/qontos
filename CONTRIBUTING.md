# Contributing to QONTOS

Thank you for your interest in contributing to QONTOS. Please see the organization-wide [Contributing Guide](https://github.com/qontos/.github/blob/main/CONTRIBUTING.md) for general guidelines.

## This Repository

This is the flagship QONTOS Python SDK. It contains:

- **`src/qontos/models/`** — Pydantic data models (circuit, partition, result, proof)
- **`src/qontos/circuit/`** — Circuit ingestion and normalization
- **`src/qontos/partitioning/`** — Circuit partitioning algorithms
- **`src/qontos/scheduling/`** — Backend scheduling and scoring
- **`src/qontos/results/`** — Result aggregation
- **`src/qontos/integrity/`** — Execution proof generation

## Quick Development Setup

```bash
git clone https://github.com/qontos/qontos.git
cd qontos
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
```

## Running Checks

```bash
make lint       # ruff check + format
make typecheck  # mypy
make test       # pytest
make check      # all of the above
```
