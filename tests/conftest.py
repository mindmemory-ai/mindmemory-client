import pytest


@pytest.fixture(autouse=True)
def _mmem_skip_dotenv_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """避免本机 ``.env`` 干扰单测；需测加载逻辑时在用例内 ``delenv``。"""
    monkeypatch.setenv("MMEM_SKIP_DOTENV", "1")
