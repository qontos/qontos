"""Import smoke tests — ensures all public API surface imports cleanly."""


def test_top_level_import():
    import qontos
    assert hasattr(qontos, "__version__")
    assert hasattr(qontos, "QontosClient")
    assert hasattr(qontos, "QontosConfig")
    assert hasattr(qontos, "AsyncQontosClient")
    assert hasattr(qontos, "QontosError")


def test_circuit_import():
    from qontos.circuit import CircuitNormalizer, CircuitValidator
    assert CircuitNormalizer is not None
    assert CircuitValidator is not None


def test_models_import():
    from qontos.models.circuit import CircuitIR, GateOperation, InputFormat
    assert CircuitIR is not None
    assert GateOperation is not None
    assert InputFormat is not None


def test_exceptions_import():
    from qontos.exceptions import (
        QontosError,
        AuthenticationError,
        ForbiddenError,
        NotFoundError,
        RateLimitError,
        ValidationError,
        ServerError,
        TimeoutError,
        CircuitError,
    )
    assert all(issubclass(e, QontosError) for e in [
        AuthenticationError, ForbiddenError, NotFoundError,
        RateLimitError, ValidationError, ServerError,
        TimeoutError, CircuitError,
    ])


def test_version_format():
    from qontos import __version__
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_no_private_imports():
    """Ensure no v1/proprietary references leak into the public package."""
    import qontos
    source_file = qontos.__file__
    assert source_file is not None
    assert "v1/proprietary" not in source_file
    assert "v1\\proprietary" not in source_file
