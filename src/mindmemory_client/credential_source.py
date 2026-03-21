"""身份来源：与 ``MMEM_CREDENTIAL_SOURCE`` 一致，避免「环境变量 + 多账户」混用歧义。"""

from __future__ import annotations

from typing import Literal

from mindmemory_client.env_loader import get_env

CredentialSource = Literal["account", "env", "none"]


def credential_source() -> CredentialSource:
    """
    - ``account``（默认）：``user_uuid`` / 私钥仅来自 ``state.json`` + ``~/.mindmemory/accounts/``。
    - ``env``：仅来自 ``MMEM_USER_UUID`` + ``MMEM_PRIVATE_KEY_PATH``（脚本/CI）。
    - ``none``：不绑定远端身份（仅本地 PNMS 等）。
    """
    raw = (get_env("MMEM_CREDENTIAL_SOURCE") or "account").strip().lower()
    if raw in ("account", "env", "none"):
        return raw  # type: ignore[return-value]
    return "account"
