"""mmem：与 LLM 对话 + PNMS 记忆；默认本地 Ollama，可配置多 profile。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.errors import MindMemoryAPIError
from mindmemory_client.llm_profiles import default_config_path, load_llm_profiles_from_toml, resolve_profile
from mindmemory_client.ollama_llm import build_ollama_llm, ollama_health

app = typer.Typer(no_args_is_help=True, help="MindMemory 客户端：PNMS + MMEM API；默认 Ollama")


def _llm_mock():
    def llm(q: str, ctx: str) -> str:
        return f"[mock] 已收到。context 长度={len(ctx)}，query 预览={q[:120]!r}"

    return llm


def _llm_echo():
    def llm(q: str, ctx: str) -> str:
        return q

    return llm


def _build_llm_callback(
    llm_mode: str,
    profile: str,
    ollama_url: Optional[str],
    model: Optional[str],
    config_path: Optional[Path],
):
    if llm_mode == "mock":
        return _llm_mock()
    if llm_mode == "echo":
        return _llm_echo()

    llm_cfg = load_llm_profiles_from_toml(config_path)
    prof = resolve_profile(
        llm_cfg,
        profile or None,
        ollama_url_override=ollama_url,
        ollama_model_override=model,
    )
    return build_ollama_llm(prof)


@app.command()
def doctor(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="mmem 配置 TOML", envvar="MMEM_CONFIG_PATH"),
) -> None:
    """检查依赖、MindMemory /health、本地 Ollama /api/tags。"""
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
            typer.echo(f"MindMemory /health: {h}")
    except MindMemoryAPIError as e:
        typer.echo(f"MindMemory /health: 不可用（{e}）", err=True)
    except Exception as e:
        typer.echo(f"MindMemory /health: 不可用（{e}）", err=True)

    if cfg.user_uuid:
        typer.echo(f"MMEM_USER_UUID: 已设置（长度 {len(cfg.user_uuid)}）")
    else:
        typer.echo("MMEM_USER_UUID: 未设置（仅本地 PNMS 时可忽略）")
    if cfg.private_key_path:
        typer.echo(f"MMEM_PRIVATE_KEY_PATH: {cfg.private_key_path}")
    else:
        typer.echo("MMEM_PRIVATE_KEY_PATH: 未设置（sync API 需要）")

    llm_cfg = load_llm_profiles_from_toml(config_path)
    prof = resolve_profile(llm_cfg, None)
    typer.echo(f"配置文件: {config_path or default_config_path()}（存在则已加载多模型）")
    typer.echo(f"当前默认 LLM profile: {llm_cfg.default_profile} → {prof.ollama_model} @ {prof.ollama_base_url}")
    try:
        tags = ollama_health(prof.ollama_base_url)
        models = tags.get("models") or []
        names = [m.get("name", "?") for m in models[:12]]
        extra = f" …共 {len(models)} 个" if len(models) > 12 else ""
        typer.echo(f"Ollama /api/tags: OK（示例: {', '.join(names)}{extra}）")
    except Exception as e:
        typer.echo(f"Ollama: 不可用（{e}）", err=True)


@app.command("models")
def list_models(
    config_path: Optional[Path] = typer.Option(None, "--config", envvar="MMEM_CONFIG_PATH"),
) -> None:
    """列出 config.toml 中的 LLM profile 与当前解析结果。"""
    path = config_path or default_config_path()
    llm_cfg = load_llm_profiles_from_toml(config_path)
    typer.echo(f"配置文件: {path} {'(存在)' if path.is_file() else '(不存在，使用内置 default)'}")
    typer.echo(f"default_profile: {llm_cfg.default_profile}")
    for name, p in sorted(llm_cfg.profiles.items()):
        typer.echo(f"  [{name}] backend={p.backend} model={p.ollama_model} url={p.ollama_base_url}")
    cur = resolve_profile(llm_cfg, None)
    typer.echo(f"解析后（默认）: {cur.ollama_model} @ {cur.ollama_base_url}")


@app.command()
def chat(
    message: Optional[str] = typer.Option(None, "-m", "--message", help="单次提问后退出"),
    agent: str = typer.Option("cli-agent", "--agent", help="Agent 名称（MMEM + PNMS 隔离）"),
    llm_mode: str = typer.Option(
        "ollama",
        "--llm",
        help="ollama（默认，读 profile）| mock | echo",
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="config.toml 中的 profile 名",
        envvar="MMEM_LLM_PROFILE",
    ),
    ollama_url: Optional[str] = typer.Option(None, "--ollama-url", envvar="MMEM_OLLAMA_URL"),
    model: Optional[str] = typer.Option(None, "--model", "-M", envvar="MMEM_OLLAMA_MODEL"),
    config_path: Optional[Path] = typer.Option(None, "--config", envvar="MMEM_CONFIG_PATH"),
    no_remote: bool = typer.Option(False, "--no-remote", help="不请求 MindMemory HTTP"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """交互对话或 -m 单次；每轮更新 PNMS 记忆。默认走本地 Ollama。"""
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
    llm_fn = _build_llm_callback(llm_mode, profile, ollama_url, model, config_path)

    if llm_mode == "ollama":
        p = resolve_profile(load_llm_profiles_from_toml(config_path), profile, ollama_url_override=ollama_url, ollama_model_override=model)
        typer.echo(f"[LLM] profile={profile!r} model={p.ollama_model} @ {p.ollama_base_url}")

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
