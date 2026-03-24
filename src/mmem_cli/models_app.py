"""``mmem models``：LLM profile 列表、写入 config.toml、本机/远程 Ollama 模型列表。"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Literal, Optional, cast

import typer

from mindmemory_client.env_loader import get_env
from mindmemory_client.llm_profiles import (
    LlmProfile,
    default_config_path,
    effective_ollama_url,
    load_llm_profiles_from_toml,
    resolve_profile,
    upsert_llm_profile,
)
from mindmemory_client.ollama_llm import ollama_health

models_app = typer.Typer(help="LLM profile：config.toml、本机/远程 Ollama")


def _mask_token(t: str | None) -> str:
    if not t:
        return "（无）"
    if len(t) <= 8:
        return "***"
    return t[:4] + "…" + t[-2:]


def _list_impl(config_path: Optional[Path]) -> None:
    path = config_path or default_config_path()
    llm_cfg = load_llm_profiles_from_toml(config_path)
    typer.echo(f"配置文件: {path} {'(存在)' if path.is_file() else '(不存在，使用内置 default)'}")
    typer.echo(f"default_profile: {llm_cfg.default_profile}")
    for name, p in sorted(llm_cfg.profiles.items()):
        typer.echo(
            f"  [{name}] target={p.target} backend={p.backend} "
            f"model={p.ollama_model} url={p.ollama_base_url} token={_mask_token(p.api_token)}"
        )
    cur = resolve_profile(llm_cfg, None)
    typer.echo(
        f"解析后（默认）: {cur.ollama_model} @ {effective_ollama_url(cur)} "
        f"token={_mask_token(cur.api_token)}"
    )


@models_app.callback(invoke_without_command=True)
def models_root(
    ctx: typer.Context,
    config_path: Optional[Path] = typer.Option(None, "--config", envvar="MMEM_CONFIG_PATH"),
) -> None:
    """不含子命令时列出 profile（与旧版 ``mmem models`` 行为一致）。"""
    if ctx.invoked_subcommand is None:
        _list_impl(config_path)
        raise typer.Exit(0)


@models_app.command("list")
def models_list(
    config_path: Optional[Path] = typer.Option(None, "--config", envvar="MMEM_CONFIG_PATH"),
) -> None:
    """列出 config.toml 中的 profile 与解析后的默认项。"""
    _list_impl(config_path)


@models_app.command("configure")
def models_configure(
    profile: str = typer.Option("default", "--profile", "-p", help="profile 名称"),
    target: str = typer.Option(
        "local",
        "--target",
        "-t",
        help="local=本机 Ollama（默认 URL 11434）；remote=自定义 URL，可配 token",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="Ollama 根 URL（无路径，如 https://ollama.com 或 http://127.0.0.1:11434）；local 默认本机",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-M",
        help="模型名；省略则用 MMEM_OLLAMA_MODEL 或内置默认 llama3.2",
        envvar="MMEM_OLLAMA_MODEL",
    ),
    api_token: Optional[str] = typer.Option(
        None,
        "--api-token",
        help="Bearer token（远程网关）；可配合 --token-stdin 自 stdin 读入",
    ),
    token_stdin: bool = typer.Option(False, "--token-stdin", help="从 stdin 读取 token（一行）"),
    no_token: bool = typer.Option(False, "--no-token", help="清除已保存的 api_token"),
    set_default: bool = typer.Option(
        True,
        "--set-default/--no-set-default",
        help="是否设为 default_profile",
    ),
    timeout_s: float = typer.Option(120.0, "--timeout", help="HTTP 超时（秒）"),
    config_path: Optional[Path] = typer.Option(None, "--config", envvar="MMEM_CONFIG_PATH"),
) -> None:
    """写入或更新 ``~/.mindmemory/config.toml`` 中的单个 profile。"""
    model_name = (model or get_env("MMEM_OLLAMA_MODEL") or LlmProfile().ollama_model).strip()
    if not model_name:
        typer.echo("请指定 --model 或设置环境变量 MMEM_OLLAMA_MODEL。", err=True)
        raise typer.Exit(1)

    if target not in ("local", "remote"):
        typer.echo("--target 须为 local 或 remote", err=True)
        raise typer.Exit(1)

    if target == "local":
        base_url = (url or "").strip() or "http://127.0.0.1:11434"
    else:
        base_url = (url or "").strip()
        if not base_url:
            typer.echo("remote 须指定 --url（Ollama 或兼容网关根地址）", err=True)
            raise typer.Exit(1)

    tok: str | None = None
    if no_token:
        tok = None
    elif token_stdin:
        line = sys.stdin.readline()
        tok = line.strip() or None
    elif api_token:
        tok = api_token.strip() or None
    elif target == "remote":
        # 可选：交互输入（仅当 TTY）
        try:
            if sys.stdin.isatty():
                use = typer.confirm("是否现在输入 API token（不会在终端回显）？", default=False)
                if use:
                    tok = getpass.getpass("API token: ").strip() or None
        except Exception:
            pass

    lp = LlmProfile(
        backend="ollama",
        target=cast(Literal["local", "remote"], target),
        ollama_base_url=base_url,
        ollama_model=model_name,
        api_token=tok,
        timeout_s=timeout_s,
    )

    out = config_path or default_config_path()
    upsert_llm_profile(config_path, profile, lp, set_default=set_default)
    typer.echo(f"已写入: {out.resolve()}")
    typer.echo(
        f"  [{profile}] target={target} model={lp.ollama_model} url={effective_ollama_url(lp)} "
        f"token={'已保存' if lp.api_token else '（无）'}"
    )
    if set_default:
        typer.echo(f"  default_profile = {profile}")


@models_app.command("tags")
def models_tags(
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="Ollama 根 URL；省略则从当前默认 profile 解析",
    ),
    api_token: Optional[str] = typer.Option(None, "--api-token", help="Bearer token"),
    config_path: Optional[Path] = typer.Option(None, "--config", envvar="MMEM_CONFIG_PATH"),
) -> None:
    """列出指定 Ollama 上已安装的模型（GET /api/tags）。"""
    headers: dict[str, str] = {}
    if api_token and api_token.strip():
        headers["Authorization"] = f"Bearer {api_token.strip()}"

    if url:
        base = url.strip().rstrip("/")
    else:
        llm_cfg = load_llm_profiles_from_toml(config_path)
        prof = resolve_profile(llm_cfg, None)
        base = effective_ollama_url(prof).rstrip("/")
        if prof.api_token and prof.api_token.strip():
            headers["Authorization"] = f"Bearer {prof.api_token.strip()}"

    try:
        tags = ollama_health(base, headers=headers)
    except Exception as e:
        typer.echo(f"请求失败: {e}", err=True)
        raise typer.Exit(1)

    models = tags.get("models") or []
    typer.echo(f"Ollama {base}/api/tags — 共 {len(models)} 个模型:")
    for m in models:
        name = m.get("name", "?")
        sz = m.get("size")
        extra = f" size={sz}" if sz is not None else ""
        typer.echo(f"  - {name}{extra}")