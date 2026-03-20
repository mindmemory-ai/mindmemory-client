"""mmem：与 LLM 对话 + PNMS 记忆；可选连接 MindMemory。"""

from __future__ import annotations

import sys
from typing import Optional

import typer

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.errors import MindMemoryAPIError

app = typer.Typer(no_args_is_help=True, help="MindMemory 客户端：PNMS + MMEM API")


def _llm_factory(mode: str):
    if mode == "mock":

        def llm(q: str, ctx: str) -> str:
            return f"[mock] 已收到。context 长度={len(ctx)}，query 预览={q[:120]!r}"

        return llm
    if mode == "echo":

        def llm2(q: str, ctx: str) -> str:
            return q

        return llm2
    typer.echo(f"未知 --llm={mode!r}，支持 mock、echo", err=True)
    raise typer.Exit(1)


@app.command()
def doctor(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """检查依赖与 MindMemory /health。"""
    typer.echo("Python:", nl=False)
    typer.echo(f" {sys.version.split()[0]}")
    try:
        import pnms  # noqa: F401

        typer.echo("pnms: 已导入")
    except ImportError:
        typer.echo("pnms: 未安装（请先 pip install -e ../pnms）", err=True)

    cfg = MindMemoryClientConfig()
    if base_url:
        cfg = cfg.model_copy(update={"base_url": base_url})
    url = cfg.base_url.rstrip("/")
    typer.echo(f"MMEM_BASE_URL: {url}")

    try:
        from mindmemory_client.api import MmemApiClient

        with MmemApiClient(cfg) as client:
            h = client.health()
            typer.echo(f"/health: {h}")
    except MindMemoryAPIError as e:
        typer.echo(f"/health 失败: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"/health 异常: {e}", err=True)
        raise typer.Exit(1)

    if cfg.user_uuid:
        typer.echo(f"MMEM_USER_UUID: 已设置（长度 {len(cfg.user_uuid)}）")
    else:
        typer.echo("MMEM_USER_UUID: 未设置（仅本地 PNMS 时可忽略）")
    if cfg.private_key_path:
        typer.echo(f"MMEM_PRIVATE_KEY_PATH: {cfg.private_key_path}")
    else:
        typer.echo("MMEM_PRIVATE_KEY_PATH: 未设置（sync API 需要）")


@app.command()
def chat(
    message: Optional[str] = typer.Option(None, "-m", "--message", help="单次提问后退出"),
    agent: str = typer.Option("cli-agent", "--agent", help="Agent 名称（MMEM + PNMS 隔离）"),
    llm: str = typer.Option("mock", "--llm", help="mock 或 echo"),
    no_remote: bool = typer.Option(False, "--no-remote", help="不请求 MindMemory HTTP"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """交互对话或 -m 单次；每轮更新 PNMS 记忆。"""
    try:
        from mindmemory_client.pnms_bridge import PnmsMemoryBridge
        from mindmemory_client.session import ChatMemorySession
    except ImportError as e:
        typer.echo(f"导入失败: {e}（请先 pip install -e ../pnms）", err=True)
        raise typer.Exit(1)

    cfg = MindMemoryClientConfig()
    if base_url:
        cfg = cfg.model_copy(update={"base_url": base_url})
    cfg = cfg.model_copy(update={"agent_name": agent})

    uid = cfg.user_uuid or "local-dev-user"
    bridge = PnmsMemoryBridge(cfg.pnms_data_root, uid, agent)
    session = ChatMemorySession(bridge)
    llm_fn = _llm_factory(llm)

    if not no_remote and cfg.user_uuid:
        try:
            from mindmemory_client.api import MmemApiClient

            with MmemApiClient(cfg) as api:
                api.health()
                typer.echo("(已连接 MindMemory /health)")
        except Exception as e:
            typer.echo(f"警告: MindMemory 不可用，继续仅本地 PNMS: {e}", err=True)

    def one_turn(q: str) -> None:
        r = session.handle_turn(q, llm_fn)
        typer.echo(r.response)
        session.save_checkpoint()

    if message is not None:
        one_turn(message)
        return

    typer.echo("交互模式；输入 exit 退出。")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        one_turn(line)


sync_app = typer.Typer(help="MindMemory 同步 API 调试")


@sync_app.command("ping")
def sync_ping(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """调用 GET /me 与 GET /agents（需 MMEM_USER_UUID）。"""
    cfg = MindMemoryClientConfig()
    if base_url:
        cfg = cfg.model_copy(update={"base_url": base_url})
    if not cfg.user_uuid:
        typer.echo("需要环境变量 MMEM_USER_UUID", err=True)
        raise typer.Exit(1)
    from mindmemory_client.api import MmemApiClient

    with MmemApiClient(cfg) as api:
        me = api.get_me(cfg.user_uuid)
        typer.echo(f"me: {me}")
        agents = api.list_agents(cfg.user_uuid)
        typer.echo(f"agents: {agents}")


app.add_typer(sync_app, name="sync")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
