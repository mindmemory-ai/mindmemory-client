"""客户端默认主目录 ``~/.mindmemory``（state、accounts、config.toml、pnms 等均相对此目录，除非环境变量覆盖）。"""

from __future__ import annotations

from pathlib import Path


def default_client_home() -> Path:
    return Path.home() / ".mindmemory"
