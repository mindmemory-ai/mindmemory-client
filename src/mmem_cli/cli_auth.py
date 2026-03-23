"""CLI 鉴权：需已解析到 user_uuid 与私钥（account 登录或 MMEM_CREDENTIAL_SOURCE=env）。"""

from __future__ import annotations

import typer

from mindmemory_client.config import MindMemoryClientConfig


def require_authenticated_user(cfg: MindMemoryClientConfig, *, hint: str | None = None) -> None:
    """对话、PNMS、同步等需先登录（``mmem account login``）或配置 env 凭证。"""
    if cfg.user_uuid and cfg.private_key_path:
        return
    msg = "请先登录账户：mmem account login（或配置 MMEM_CREDENTIAL_SOURCE=env 与 MMEM_USER_UUID / MMEM_PRIVATE_KEY_PATH）。"
    if hint:
        msg = f"{hint} {msg}"
    typer.echo(msg, err=True)
    raise typer.Exit(1)
