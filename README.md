<div align="center">

<img src="assets/qontos-logo.png" alt="QONTOS" width="400">

<br>

**Quantum Orchestrated Network for Transformative Optimization Systems**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10+-yellow.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![CI](https://img.shields.io/github/actions/workflow/status/qontos/qontos/ci.yml?branch=main&label=CI&logo=github)](https://github.com/qontos/qontos/actions)
[![PyPI](https://img.shields.io/pypi/v/qontos.svg?logo=pypi&logoColor=white)](https://pypi.org/project/qontos/)

An open-source Python SDK for modular quantum orchestration across external backends and future native QONTOS systems.

[Installation](#installation) &middot;
[Quick Start](#quick-start) &middot;
[Architecture](#architecture) &middot;
[Documentation](#documentation) &middot;
[Examples](https://github.com/qontos/qontos-examples) &middot;
[Contributing](#contributing) &middot;
[Citing QONTOS](#citing-qontos)

</div>

---

## What is QONTOS?

QONTOS is the flagship Python SDK for modular quantum computing orchestration. It provides a unified developer interface for circuit ingestion, partitioning, scheduling, distributed execution, result aggregation, and execution integrity.

The SDK interoperates with external providers today and is designed to become the software interface for future native QONTOS modular quantum hardware.

1. **Ingest** circuits in any format (OpenQASM 2.0/3.0, Qiskit, PennyLane)
2. **Partition** large circuits across quantum modules using graph-based algorithms
3. **Schedule** partitions to optimal backends based on fidelity, cost, and queue depth
4. **Execute** across multiple providers simultaneously (IBM Quantum, Amazon Braket, simulators)
5. **Aggregate** distributed results with mathematically grounded reconstruction
6. **Verify** execution integrity with a three-layer SHA-256 cryptographic proof chain

## Installation

```bash
pip install qontos
```

For quantum backend support:

```bash
pip install "qontos[ibm]"       # IBM Quantum via Qiskit
pip install "qontos[braket]"    # Amazon Braket
pip install "qontos[all]"       # Everything
```

Requires Python 3.10 or later.

## Quick Start

### Run a circuit on a local simulator

```python
from qontos import QontosClient
from qontos.circuit import CircuitNormalizer

# Normalize an OpenQASM circuit
normalizer = CircuitNormalizer()
circuit_ir = normalizer.normalize("""
    OPENQASM 2.0;
    include "qelib1.inc";
    qreg q[3];
    creg c[3];
    h q[0];
    cx q[0], q[1];
    cx q[0], q[2];
    measure q -> c;
""")

print(f"Circuit: {circuit_ir.num_qubits} qubits, depth {circuit_ir.depth}")
# Circuit: 3 qubits, depth 3
```

### Partition a circuit for modular execution

```python
from qontos.partitioning import Partitioner, PartitionConstraints

partitioner = Partitioner()
plan = partitioner.partition(
    circuit_ir,
    constraints=PartitionConstraints(max_qubits_per_partition=2)
)

for entry in plan.partitions:
    print(f"Partition {entry.partition_id}: qubits {entry.qubit_indices}")
# Partition 0: qubits [0, 1]
# Partition 1: qubits [2]
```

### Score and schedule backends

```python
from qontos.scheduling import Scheduler

scheduler = Scheduler()
assignments = scheduler.schedule(plan, available_backends)

for task in assignments:
    print(f"Partition {task.partition_id} → {task.backend_name} (score: {task.score:.3f})")
```

### Generate execution proofs

```python
from qontos.integrity import ExecutionHasher

hasher = ExecutionHasher()
proof = hasher.compute_proof(manifest, plan, result)
print(f"Proof hash: {proof.proof_hash}")
# Proof hash: sha256:a3f2c1...
```

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         User Application                            │
│                  (Qiskit / PennyLane / OpenQASM)                   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│                            qontos SDK                              │
│                                                                    │
│  ┌──────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐   │
│  │ Circuit   │→ │ Partition   │→ │ Execution   │→ │ Result +      │   │
│  │ Ingest    │  │ Planning    │  │ Routing     │  │ Integrity     │   │
│  │           │  │             │  │ + Scheduling│  │ Verification  │   │
│  └──────────┘  └────────────┘  └────────────┘  └──────────────┘   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
          ┌────────────────────┴────────────────────┐
          │                                         │
┌─────────▼──────────────────────┐     ┌────────────▼────────────────────────┐
│      External Execution Plane   │     │      Native QONTOS Execution Plane │
│                                  │     │              (future)              │
│  IBM Quantum  │  Braket          │     │  Modular QPUs  │  Control Stack    │
│  Simulators   │  Custom Adapter  │     │  FTQC Runtime  │  Interconnects    │
└─────────┬───────────────────────┘     └────────────┬────────────────────────┘
          │                                          │
          └────────────────────┬─────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│                       Unified QONTOS Outcome                        │
│            Partition outcomes, aggregation, and proof chain         │
└────────────────────────────────────────────────────────────────────┘
```

QONTOS works with external providers today, while the SDK and execution model are being shaped to serve future native QONTOS modular quantum hardware through the same circuit, partitioning, scheduling, and verification surface.

### Package Layout

| Module | Purpose |
|---|---|
| `qontos.circuit` | Multi-format circuit ingestion and normalization |
| `qontos.models` | Pydantic v2 data models for circuits, partitions, results, proofs |
| `qontos.partitioning` | Graph-based circuit partitioning (greedy, spectral, manual) |
| `qontos.scheduling` | Multi-criteria backend scoring and assignment |
| `qontos.results` | Distributed result aggregation and reconstruction |
| `qontos.integrity` | SHA-256 execution proof generation |

### Partitioning Strategies

| Strategy | Complexity | Best For |
|---|---|---|
| `GreedyPartitioner` | O(n) | Circuits < 20 qubits, fast iteration |
| `SpectralPartitioner` | O(n log n) | Larger circuits, minimizes inter-partition gates |
| `ManualPartitioner` | O(1) | User-specified qubit-to-module mapping |

Strategy is auto-selected based on circuit size. Override via `PartitionConstraints.preferred_strategy`.

### Scheduling Weights

| Factor | Default Weight | Description |
|---|---|---|
| Fidelity | 0.60 | Backend gate fidelity match |
| Queue depth | 0.15 | Backend availability |
| Cost | 0.10 | Normalized cost-per-shot |
| Capacity | 0.15 | Qubit count fit |

Configurable per-policy via `ScoringWeights`.

## Supported Formats

| Format | Input | Notes |
|---|---|---|
| OpenQASM 2.0 | `str` | Parsed via Qiskit |
| OpenQASM 3.0 | `str` | Parsed via `qiskit.qasm3` |
| Qiskit | `QuantumCircuit` | Native support |
| PennyLane | JSON tape | Via translator |

## Supported Backends

| Backend | Package | Provider |
|---|---|---|
| Qiskit Aer (Simulator) | `qontos` | Local |
| IBM Quantum | `qontos[ibm]` | IBM |
| Amazon Braket | `qontos[braket]` | AWS |
| Native QONTOS Systems | planned | Future native execution target |
| Custom | Implement `ExecutorContract` | Any |

### Building a Custom Executor

```python
from qontos.models import ExecutorInput, ExecutorOutput, ExecutorError

class MyExecutor:
    """Implement the ExecutorContract interface."""

    def validate(self, input: ExecutorInput) -> list[str]:
        """Return list of validation issues, empty if valid."""
        ...

    def submit(self, input: ExecutorInput) -> ExecutorOutput:
        """Submit circuit for execution."""
        ...

    def poll(self, provider_job_id: str) -> str:
        """Poll async job status. Return 'completed', 'running', or 'failed'."""
        ...

    def cancel(self, provider_job_id: str) -> bool:
        """Cancel a running job."""
        ...

    def normalize_result(self, raw: dict, partition_id: str) -> ExecutorOutput:
        """Convert provider-specific result to ExecutorOutput."""
        ...

    def normalize_error(self, raw: dict, partition_id: str) -> ExecutorError:
        """Convert provider-specific error to ExecutorError."""
        ...
```

## Related Repositories

| Repository | Description |
|------------|-------------|
| [qontos](https://github.com/qontos/qontos) | Flagship Python SDK |
| [qontos-sim](https://github.com/qontos/qontos-sim) | Simulators and digital twin |
| [qontos-examples](https://github.com/qontos/qontos-examples) | Tutorials and examples |
| [qontos-benchmarks](https://github.com/qontos/qontos-benchmarks) | Benchmark evidence |
| [qontos-research](https://github.com/qontos/qontos-research) | Research papers and roadmap |

## Documentation

- [API Reference](https://docs.qontos.io/api)
- [User Guide](https://docs.qontos.io/guide)
- [Architecture Overview](https://docs.qontos.io/architecture)
- [Examples Repository](https://github.com/qontos/qontos-examples)

## Stability

QONTOS follows [Semantic Versioning](https://semver.org/). The current release is **0.x** (pre-1.0), meaning the public API may change between minor versions. We aim for API stability and will document all breaking changes in the [CHANGELOG](CHANGELOG.md).

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

```bash
git clone https://github.com/qontos/qontos.git
cd qontos
pip install -e ".[dev]"
make check  # lint + typecheck + test
```

## Citing QONTOS

If you use QONTOS in your research, please cite:

```bibtex
@software{qontos2026,
  title     = {QONTOS: Quantum Orchestrated Network for Transformative Optimization Systems},
  author    = {Tamilselvan, Ramesh},
  year      = {2026},
  url       = {https://github.com/qontos/qontos},
  license   = {Apache-2.0}
}
```

## License

[Apache License 2.0](LICENSE)

---

*Built by [Zhyra Quantum Research Institute (ZQRI)](https://zhyra.xyz) — Abu Dhabi, UAE*
