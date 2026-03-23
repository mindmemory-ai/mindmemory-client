"""``MindMemoryClientConfig.from_env`` 与默认路径。"""

import pytest

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.env_loader import reset_dotenv_loaded


def test_from_env_default_pnms_root_is_client_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_PNMS_DATA_ROOT", raising=False)
    monkeypatch.delenv("MMEM_CREDENTIAL_SOURCE", raising=False)
    monkeypatch.delenv("MMEM_USER_UUID", raising=False)
    monkeypatch.delenv("MMEM_PRIVATE_KEY_PATH", raising=False)
    fake_home = tmp_path / "h"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    reset_dotenv_loaded()
    c = MindMemoryClientConfig.from_env()
    assert c.pnms_data_root == fake_home / ".mindmemory"
    assert c.user_uuid is None
