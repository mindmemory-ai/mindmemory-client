"""客户端主目录 ``~/.mindmemory``。"""

from pathlib import Path

import pytest

from mindmemory_client.client_home import default_client_home


def test_default_client_home_respects_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "h"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    assert default_client_home() == fake_home / ".mindmemory"
