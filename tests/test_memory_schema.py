"""memory_schema_version 与 PNMS get_memory_format_version 对齐。"""

import pytest

from mindmemory_client.memory_schema import resolve_memory_schema_version


def test_cli_override_wins() -> None:
    assert resolve_memory_schema_version("v9") == "v9"


def test_pnms_api_when_no_cli() -> None:
    try:
        from pnms import get_memory_format_version
    except ImportError:
        assert resolve_memory_schema_version(None) == "1.0.0"
    else:
        assert resolve_memory_schema_version(None) == get_memory_format_version()
