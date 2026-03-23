"""客户端目录：配置（state、账户元数据）与数据（PNMS 根目录）。"""

from __future__ import annotations

import os
from pathlib import Path

from mindmemory_client.client_home import default_client_home
from mindmemory_client.env_loader import ensure_dotenv_loaded


def client_config_dir() -> Path:
    """默认 ``~/.mindmemory``；可用 ``MMEM_CLIENT_CONFIG_DIR`` 覆盖。"""
    ensure_dotenv_loaded()
    p = os.environ.get("MMEM_CLIENT_CONFIG_DIR")
    return Path(p).expanduser() if p else default_client_home()


def client_data_dir() -> Path:
    """默认与 ``client_config_dir`` 相同（``~/.mindmemory``）；可用 ``MMEM_CLIENT_DATA_DIR`` 单独指定数据根。"""
    ensure_dotenv_loaded()
    p = os.environ.get("MMEM_CLIENT_DATA_DIR")
    return Path(p).expanduser() if p else default_client_home()


def accounts_config_dir() -> Path:
    return client_config_dir() / "accounts"


def state_path() -> Path:
    return client_config_dir() / "state.json"


def account_dir(user_uuid: str) -> Path:
    return accounts_config_dir() / user_uuid


def account_private_key_path(user_uuid: str) -> Path:
    """OpenSSH Ed25519 私钥文件路径。"""
    return account_dir(user_uuid) / "id_ed25519"


def account_meta_path(user_uuid: str) -> Path:
    return account_dir(user_uuid) / "account.json"


def default_pnms_data_root() -> Path:
    """
    兼容旧版：PNMS checkpoint 现统一为 ``accounts/<uuid>/agents/<agent>/pnms``。
    保留 ``…/pnms`` 子目录仅作兼容或第三方脚本参考。
    """
    return client_data_dir() / "pnms"
