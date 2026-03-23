# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-23

### Added
- Initial public release of the QONTOS Python SDK
- Multi-format circuit ingestion (OpenQASM 2.0/3.0, Qiskit, PennyLane)
- Circuit partitioning with greedy, spectral, and manual strategies
- Capability-aware backend scheduling with multi-criteria scoring
- Result aggregation with passthrough, independent, and entangled merge
- Cryptographic execution proofs via three-layer SHA-256 hash chain
- Pydantic v2 data models for circuits, partitions, results, and proofs
- Full type annotations and mypy strict compliance
