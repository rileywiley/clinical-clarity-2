"""Placeholder smoke test — proves pytest is wired before Phase 1 starts."""

import engine


def test_engine_import() -> None:
    assert engine.__version__ == "0.1.0"
