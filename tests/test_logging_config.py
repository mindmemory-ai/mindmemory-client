import logging

import pytest

from mindmemory_client.logging_config import (
    configure_client_logging,
    reset_client_logging_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    reset_client_logging_for_tests()


def test_configure_respects_mmem_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.setenv("MMEM_LOG_LEVEL", "DEBUG")
    configure_client_logging()
    assert logging.getLogger("mindmemory_client").level == logging.DEBUG
    assert logging.getLogger("mmem_cli").level == logging.DEBUG


def test_configure_invalid_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.setenv("MMEM_LOG_LEVEL", "not-a-level")
    configure_client_logging()
    assert logging.getLogger("mindmemory_client").level == logging.INFO


def test_configure_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.setenv("MMEM_LOG_LEVEL", "WARNING")
    configure_client_logging()
    configure_client_logging()
    assert logging.getLogger("mindmemory_client").level == logging.WARNING
    assert len(logging.getLogger("mindmemory_client").handlers) == 1
