"""从 ``.env`` 合并到 ``os.environ``（与 mindmemory 后端 ``pydantic-settings`` + ``env_file`` 思路一致，便于外部用文件控制变量）。"""

from __future__ import annotations

import os
from pathlib import Path

from mindmemory_client.client_home import default_client_home

_DOTENV_LOADED = False


def discover_dotenv_paths() -> list[Path]:
    """
    解析待加载的 ``.env`` 路径（按顺序加载，后者在 ``override=True`` 时覆盖前者）。

    - 若设置 ``MMEM_ENV_FILE``：仅使用该文件（存在则加载）。
    - 否则：先 ``~/.mindmemory/.env``（用户级），再 ``cwd/.env``（项目级覆盖）。
    """
    explicit = os.environ.get("MMEM_ENV_FILE")
    if explicit:
        p = Path(explicit).expanduser()
        return [p] if p.is_file() else []

    out: list[Path] = []
    user = default_client_home() / ".env"
    if user.is_file():
        out.append(user)
    cwd = Path.cwd() / ".env"
    if cwd.is_file():
        out.append(cwd)
    return out


def load_mmem_dotenv(*, override: bool = False) -> None:
    from dotenv import load_dotenv

    paths = discover_dotenv_paths()
    if not paths:
        return
    if os.environ.get("MMEM_ENV_FILE"):
        load_dotenv(paths[0], override=override)
        return
    if len(paths) == 1:
        load_dotenv(paths[0], override=override)
        return
    if len(paths) >= 2:
        load_dotenv(paths[0], override=False)
        load_dotenv(paths[1], override=True)


def reset_dotenv_loaded() -> None:
    """测试用：允许再次扫描 ``.env``。"""
    global _DOTENV_LOADED
    _DOTENV_LOADED = False


def ensure_dotenv_loaded() -> None:
    """
    幂等：将 ``.env`` 合并进环境变量（``override=False`` 时不覆盖已存在的键，便于 shell 与 CI 优先）。
    若 ``MMEM_SKIP_DOTENV=1``（pytest 默认）则跳过。
    """
    global _DOTENV_LOADED
    if os.environ.get("MMEM_SKIP_DOTENV") == "1":
        return
    if _DOTENV_LOADED:
        return
    load_mmem_dotenv(override=False)
    _DOTENV_LOADED = True


def get_env(name: str, default: str | None = None) -> str | None:
    """读取环境变量（先 ``ensure_dotenv_loaded``）。"""
    ensure_dotenv_loaded()
    return os.environ.get(name, default)
