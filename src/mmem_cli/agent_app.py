"""``mmem agent``：账号下 Agent 工作区（PNMS + 记忆 Git 仓库）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

import json

from mindmemory_client.agent_workspace import (
    agent_git_dir,
    agent_workspace_dir,
    ensure_agent_registered_on_server,
    git_clone_memory_repo,
    list_local_agent_names,
    list_local_agent_workspaces,
    load_agent_config,
    memory_repo_ssh_url,
    resolve_workspace_dir_for_user_agent,
    write_agent_config,
)
from mindmemory_client.client_state import load_state, resolve_mmem_config, save_state
from mindmemory_client.config import DEFAULT_AGENT_NAME, MindMemoryClientConfig
from mmem_cli.cli_auth import require_authenticated_user
from mindmemory_client.env_loader import get_env

agent_app = typer.Typer(no_args_is_help=True, help="Agent 工作区：PNMS 目录与记忆 Git 仓库")


@agent_app.command("list")
def agent_list(
    remote: bool = typer.Option(False, "--remote", "-r", help="同时请求 MindMemory GET /api/v1/agents"),
    json_out: bool = typer.Option(False, "--json", help="JSON 输出"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """列出本机已初始化的 Agent；可选拉取服务端登记的全部 Agent。"""
    cfg = resolve_mmem_config(base_url_override=base_url)
    require_authenticated_user(cfg)
    st = load_state()
    current = cfg.agent_name
    uid = cfg.user_uuid

    local_rows: list[dict[str, str]] = []
    if uid:
        for n, ws in list_local_agent_workspaces(uid):
            mark = "*" if n == current else " "
            local_rows.append({"name": n, "workspace": str(ws.resolve()), "current": mark})

    remote_payload: list[dict[str, object]] | None = None
    if remote:
        if not uid or not cfg.private_key_path:
            typer.echo("需要已登录账户（mmem account login）或 env 凭证才能请求远端。", err=True)
            raise typer.Exit(1)
        try:
            from mindmemory_client.api import MmemApiClient

            with MmemApiClient(cfg) as api:
                raw = api.list_agents(uid)
            remote_payload = list(raw.get("agents") or [])
        except Exception as e:
            typer.echo(f"远端列表失败: {e}", err=True)
            raise typer.Exit(1)

    if json_out:
        out: dict[str, object] = {
            "current_agent_name": st.current_agent_name,
            "resolved_default": current,
            "local": local_rows,
        }
        if remote_payload is not None:
            out["remote_agents"] = remote_payload
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        return

    typer.echo(f"当前 CLI 默认 Agent: {current}")
    if st.current_agent_name:
        typer.echo("（来自 state.json 中 current_agent_name；可用 mmem agent unset 恢复默认名）")
    else:
        typer.echo("（未设置 current_agent_name，与内置默认 BT-7274 一致）")

    typer.echo("")
    typer.echo("本机工作区（* = 与当前默认同名）:")
    if not local_rows:
        typer.echo("  （无）可先执行: mmem agent init <名称>")
    else:
        for row in local_rows:
            typer.echo(f"  {row['current']} {row['name']}")
            typer.echo(f"      {row['workspace']}")

    if remote_payload is not None:
        typer.echo("")
        typer.echo("服务端登记:")
        if not remote_payload:
            typer.echo("  （无）")
        else:
            for a in remote_payload:
                nm = a.get("agent_name", "?")
                mc = a.get("memory_count", "?")
                rp = a.get("repo_path") or ""
                typer.echo(f"  - {nm}  memories={mc}  repo={rp}")


@agent_app.command("current")
def agent_current(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """打印当前 CLI 将使用的默认 Agent 名（state + 解析结果）。"""
    st = load_state()
    cfg = resolve_mmem_config(base_url_override=base_url)
    typer.echo(f"state.current_agent_name: {st.current_agent_name!r}")
    typer.echo(f"解析后 agent_name: {cfg.agent_name!r}")
    typer.echo(f"内置默认（无 state 时）: {MindMemoryClientConfig.from_env().agent_name!r}")


@agent_app.command("use")
def agent_use(
    name: str = typer.Argument(..., help="设为默认 Agent 名称（mmem chat / pnms / sync 等省略 --agent 时）"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """将默认 Agent 写入 state.json；需与本机或远端将使用的名称一致。"""
    name = name.strip()
    if not name:
        typer.echo("名称不能为空。", err=True)
        raise typer.Exit(1)

    cfg = resolve_mmem_config(base_url_override=base_url)
    require_authenticated_user(cfg)
    uid = cfg.user_uuid
    if uid:
        local = set(list_local_agent_names(uid))
        if name not in local:
            typer.echo(
                f"提示: 本机尚未发现工作区「{name}」。可执行 mmem agent init {name}，"
                "若仅在远端存在仍可继续 use。",
                err=True,
            )

    st = load_state()
    st.current_agent_name = name
    save_state(st)
    typer.echo(f"已设置默认 Agent 为 {name!r}（写入 state.json）")


@agent_app.command("unset")
def agent_unset() -> None:
    """清除 state 中的默认 Agent，恢复为内置默认名 BT-7274。"""
    st = load_state()
    st.current_agent_name = None
    save_state(st)
    typer.echo(f"已清除 current_agent_name，默认 Agent 恢复为 {DEFAULT_AGENT_NAME!r}。")


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
    require_authenticated_user(cfg)

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

    st = load_state()
    st.current_agent_name = name
    save_state(st)
    typer.echo(f"已设为当前默认 Agent（mmem chat / sync 等可省略 --agent）：{name!r}")

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
    require_authenticated_user(cfg)
    uid = cfg.user_uuid
    assert uid is not None
    ws = agent_workspace_dir(uid, name)
    typer.echo(f"工作区: {ws.resolve()}")
    typer.echo(f"PNMS:   {(ws / 'pnms').resolve()}")
    typer.echo(f"Git:    {(ws / 'repo').resolve()}")
    typer.echo(f"workspace 源文件池: {resolve_workspace_dir_for_user_agent(uid, name).resolve()}")
    meta = load_agent_config(uid, name)
    if meta:
        typer.echo(f"agent.json: git_ssh_url={meta.get('git_ssh_url')}")
    else:
        typer.echo("agent.json: 无（尚未 mmem agent init）")
