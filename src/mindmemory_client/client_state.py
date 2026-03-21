"""多账户状态：当前账户、本地账户目录、与 ``MindMemoryClientConfig`` 合并解析。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mindmemory_client.client_paths import (
    account_meta_path,
    account_private_key_path,
    accounts_config_dir,
    client_config_dir,
    client_data_dir,
    default_pnms_data_root,
    state_path,
)
from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.credential_source import credential_source
from mindmemory_client.env_loader import get_env


@dataclass
class ClientState:
    version: int = 1
    current_account_uuid: str | None = None


@dataclass
class AccountMeta:
    email: str
    user_uuid: str
    created_at: str | None = None


def load_state() -> ClientState:
    p = state_path()
    if not p.is_file():
        return ClientState()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ClientState()
    return ClientState(
        version=int(raw.get("version", 1)),
        current_account_uuid=raw.get("current_account_uuid"),
    )


def save_state(state: ClientState) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": state.version,
        "current_account_uuid": state.current_account_uuid,
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_account_meta(user_uuid: str) -> AccountMeta | None:
    mp = account_meta_path(user_uuid)
    if not mp.is_file():
        return None
    try:
        raw = json.loads(mp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    email = raw.get("email")
    uid = raw.get("user_uuid")
    if not email or not uid:
        return None
    return AccountMeta(
        email=str(email).strip().lower(),
        user_uuid=str(uid),
        created_at=raw.get("created_at"),
    )


def save_account_meta(meta: AccountMeta) -> None:
    mp = account_meta_path(meta.user_uuid)
    mp.parent.mkdir(parents=True, exist_ok=True)
    created = meta.created_at or datetime.now(timezone.utc).isoformat()
    mp.write_text(
        json.dumps(
            {
                "email": meta.email,
                "user_uuid": meta.user_uuid,
                "created_at": created,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_private_key_file(user_uuid: str, private_key_openssh: str) -> Path:
    """写入私钥文件并尽量 chmod 600。"""
    path = account_private_key_path(user_uuid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(private_key_openssh.rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def list_local_accounts() -> list[AccountMeta]:
    root = accounts_config_dir()
    if not root.is_dir():
        return []
    out: list[AccountMeta] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        uid = child.name
        m = load_account_meta(uid)
        if m:
            out.append(m)
    return out


def find_account_by_email(email: str) -> AccountMeta | None:
    e = email.strip().lower()
    for m in list_local_accounts():
        if m.email == e:
            return m
    return None


def has_local_private_key(user_uuid: str) -> bool:
    p = account_private_key_path(user_uuid)
    return p.is_file() and p.stat().st_size > 0


def resolve_mmem_config(
    *,
    base_url_override: str | None = None,
    agent_name_override: str | None = None,
) -> MindMemoryClientConfig:
    """
    解析最终配置，与 ``MMEM_CREDENTIAL_SOURCE`` 一致：

    - ``env``：身份仅来自 ``MMEM_USER_UUID`` + ``MMEM_PRIVATE_KEY_PATH``（见 ``from_env``）。
    - ``none``：不绑定远端身份（无 uuid/私钥）。
    - ``account``（默认）：若 ``state.json`` 指向的本地账户目录完整，则合并该账户；否则等同 ``none`` 侧的无凭证状态。
    """
    base = MindMemoryClientConfig.from_env()
    if base_url_override:
        base = base.model_copy(update={"base_url": base_url_override})
    if agent_name_override:
        base = base.model_copy(update={"agent_name": agent_name_override})

    src = credential_source()
    if src in ("env", "none"):
        return base

    st = load_state()
    uid = st.current_account_uuid
    if not uid:
        return base

    meta = load_account_meta(uid)
    pk = account_private_key_path(uid)
    if not meta or not pk.is_file():
        return base

    pnms_root = Path(get_env("MMEM_PNMS_DATA_ROOT") or default_pnms_data_root())
    return base.model_copy(
        update={
            "user_uuid": meta.user_uuid,
            "private_key_path": pk,
            "pnms_data_root": pnms_root,
        }
    )


def ensure_client_dirs() -> None:
    """创建配置根目录与数据根目录（幂等）。"""
    client_config_dir().mkdir(parents=True, exist_ok=True)
    client_data_dir().mkdir(parents=True, exist_ok=True)
    accounts_config_dir().mkdir(parents=True, exist_ok=True)
    default_pnms_data_root().mkdir(parents=True, exist_ok=True)
