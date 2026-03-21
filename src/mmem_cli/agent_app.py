"""``mmem agent``：账号下 Agent 工作区（PNMS + 记忆 Git 仓库）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from mindmemory_client.agent_workspace import (
    agent_git_dir,
    agent_workspace_dir,
    ensure_agent_registered_on_server,
    git_clone_memory_repo,
    load_agent_config,
    memory_repo_ssh_url,
    write_agent_config,
)
from mindmemory_client.client_state import resolve_mmem_config
from mindmemory_client.env_loader import get_env

agent_app = typer.Typer(no_args_is_help=True, help="Agent 工作区：PNMS 目录与记忆 Git 仓库")


def _ssh_host(host: Optional[str]) -> str:
    h = (host or get_env("MMEM_GIT_SSH_HOST") or "").strip()
    if not h:
        typer.echo(
            "请设置 MMEM_GIT_SSH_HOST（Gogs SSH 主机名，如 gogs.example.com）"
            "或使用 --ssh-host。",
            err=True,
        )
        raise typer.Exit(1)
    return h


def _ssh_port(raw: Optional[str]) -> int | None:
    if not raw:
        p = get_env("MMEM_GIT_SSH_PORT")
        raw = (p or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        typer.echo(f"无效的 SSH 端口: {raw}", err=True)
        raise typer.Exit(1)


@agent_app.command("init")
def agent_init(
    name: str = typer.Argument(..., help="Agent 名称（与 MindMemory / OpenClaw 中一致）"),
    ssh_host: Optional[str] = typer.Option(None, "--ssh-host", help="覆盖 MMEM_GIT_SSH_HOST"),
    ssh_port: Optional[str] = typer.Option(None, "--ssh-port", help="覆盖 MMEM_GIT_SSH_PORT（非默认 22 时）"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
    skip_register: bool = typer.Option(
        False,
        "--skip-register",
        help="不向服务端请求 begin-submit（仅本地目录与 agent.json；远端尚未建仓时需去掉此选项）",
    ),
    skip_clone: bool = typer.Option(False, "--skip-clone", help="仅创建目录与配置，不 git clone"),
) -> None:
    """
    在当前账号下创建 ``accounts/<user_uuid>/agents/<name>/``（含 ``pnms/``、``repo/``）。

    默认：调用 MindMemory ``begin-submit`` 以在服务端创建 Agent 与 Gogs 仓库（若尚不存在），
    立即 ``mark_completed(failure)`` 释放锁；再按约定 SSH URL ``git clone`` 到 ``repo/``。
    """
    cfg = resolve_mmem_config(base_url_override=base_url)
    if not cfg.user_uuid or not cfg.private_key_path:
        typer.echo("需要已登录账户（mmem account login）或 MMEM_CREDENTIAL_SOURCE=env + 私钥。", err=True)
        raise typer.Exit(1)

    host = _ssh_host(ssh_host)
    port = _ssh_port(ssh_port)
    url = memory_repo_ssh_url(cfg.user_uuid, name, ssh_host=host)

    if not skip_register:
        try:
            begin = ensure_agent_registered_on_server(cfg, name)
            if begin.get("agent_created"):
                typer.echo("服务端已新建 Agent 与仓库。")
            else:
                typer.echo("服务端已存在该 Agent。")
        except Exception as e:
            typer.echo(f"服务端注册失败（可检查网络与 MMEM_BASE_URL）: {e}", err=True)
            raise typer.Exit(1)

    write_agent_config(cfg.user_uuid, name, ssh_host=host, ssh_port=port, git_ssh_url=url)
    typer.echo(f"已写入 {agent_workspace_dir(cfg.user_uuid, name) / 'agent.json'}")

    repo = agent_git_dir(cfg.user_uuid, name)
    if skip_clone:
        typer.echo(f"已跳过 clone。记忆仓库 URL: {url}")
        typer.echo(f"可稍后: git clone（或再次运行不带 --skip-clone）")
        return

    if (repo / ".git").exists():
        typer.echo(f"已存在 {repo}，跳过 clone。")
        return

    try:
        git_clone_memory_repo(
            remote_url=url,
            dest=repo,
            private_key_path=Path(cfg.private_key_path),
            ssh_port=port,
        )
        typer.echo(f"已 clone 到 {repo.resolve()}")
    except Exception as e:
        typer.echo(f"git clone 失败: {e}", err=True)
        typer.echo(f"请检查 MMEM_GIT_SSH_HOST、公钥是否已上传到 Gogs，以及远端是否已建仓。", err=True)
        raise typer.Exit(1)


@agent_app.command("info")
def agent_info(
    name: str = typer.Argument(..., help="Agent 名称"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """打印该 Agent 工作区路径、PNMS 目录、记忆仓库目录与已保存的 SSH URL。"""
    cfg = resolve_mmem_config(base_url_override=base_url)
    uid = cfg.user_uuid
    if not uid:
        typer.echo("需要已登录账户。", err=True)
        raise typer.Exit(1)
    ws = agent_workspace_dir(uid, name)
    typer.echo(f"工作区: {ws.resolve()}")
    typer.echo(f"PNMS:   {(ws / 'pnms').resolve()}")
    typer.echo(f"Git:    {(ws / 'repo').resolve()}")
    meta = load_agent_config(uid, name)
    if meta:
        typer.echo(f"agent.json: git_ssh_url={meta.get('git_ssh_url')}")
    else:
        typer.echo("agent.json: 无（尚未 mmem agent init）")
