"""mmem：与 LLM 对话 + PNMS 记忆；默认本地 Ollama，可配置多 profile。"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import time
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


sync_app = typer.Typer(help="MindMemory 同步：API、记忆 AES-GCM、git 推送")


def _git_remote_origin_url(git_dir: Path) -> str:
    out = subprocess.check_output(
        ["git", "-C", str(git_dir), "remote", "get-url", "origin"],
        text=True,
    )
    return out.strip()


def _validate_remote_url_for_user(remote_url: str, user_uuid: str) -> None:
    """Gogs 用户名为 user_uuid 去掉连字符，远端 URL 应包含该片段以防推错仓库。"""
    needle = user_uuid.replace("-", "").lower()
    if needle not in remote_url.lower():
        raise ValueError(
            f"origin 远端 URL 中未找到 Gogs 用户名片段（{needle[:12]}…），"
            "请检查 git remote 是否指向该 user_uuid 下的仓库，或使用 --skip-remote-check 跳过。"
        )


def _git_pull_rebase_origin(git_dir: Path, branch: str) -> tuple[bool, str]:
    """
    git pull --rebase origin <branch>。
    首次推送远端尚无分支时允许失败并继续。
    返回 (ok, message)。
    """
    pr = subprocess.run(
        ["git", "-C", str(git_dir), "pull", "--rebase", "origin", branch],
        capture_output=True,
        text=True,
    )
    err = (pr.stderr or "") + (pr.stdout or "")
    if pr.returncode == 0:
        return True, "pull --rebase: 已同步远端"
    low = err.lower()
    if any(
        x in low
        for x in (
            "couldn't find remote ref",
            "could not find remote ref",
            "no tracking information",
            "fatal: couldn't find remote ref",
            "fatal: not a valid object name",
        )
    ):
        return True, "pull --rebase: 跳过（远端尚无该分支或首次推送）"
    return False, err.strip() or f"exit {pr.returncode}"


def _pack_pnms_dir_to_encrypted_b64(pnms_dir: Path, key: bytes) -> str:
    """将目录打成 tar.gz 后 AES-GCM 加密为 Base64 单行。"""
    from mindmemory_client.memory_crypto import encrypt_memory_base64

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(pnms_dir, arcname=pnms_dir.name)
    raw = buf.getvalue()
    return encrypt_memory_base64(raw, key)


@sync_app.command("encrypt-file")
def sync_encrypt_file(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    output_path: Optional[Path] = typer.Option(None, "-o", "--output", help="默认 stdout"),
    private_key: Path = typer.Option(
        ...,
        "--private-key",
        envvar="MMEM_PRIVATE_KEY_PATH",
        help="OpenSSH 私钥路径（与 gen_register_bundle 一致）",
    ),
) -> None:
    """明文文件 → AES-256-GCM（K_seed）→ Base64 单行。"""
    from mindmemory_client.keys import read_openssh_private_key_pem
    from mindmemory_client.memory_crypto import encrypt_memory_base64
    from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

    pem = read_openssh_private_key_pem(private_key)
    key = k_seed_bytes_from_private_key_openssh(pem)
    data = input_path.read_bytes()
    b64 = encrypt_memory_base64(data, key)
    if output_path:
        output_path.write_text(b64 + "\n", encoding="utf-8")
        typer.echo(f"已写入 {output_path}")
    else:
        typer.echo(b64)


@sync_app.command("decrypt-file")
def sync_decrypt_file(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    output_path: Optional[Path] = typer.Option(None, "-o", "--output", help="默认 stdout 二进制"),
    private_key: Path = typer.Option(
        ...,
        "--private-key",
        envvar="MMEM_PRIVATE_KEY_PATH",
    ),
) -> None:
    """Base64 密文文件 → 明文（与 encrypt-file 配对）。"""
    from mindmemory_client.keys import read_openssh_private_key_pem
    from mindmemory_client.memory_crypto import decrypt_memory_base64
    from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

    pem = read_openssh_private_key_pem(private_key)
    key = k_seed_bytes_from_private_key_openssh(pem)
    b64 = input_path.read_text(encoding="utf-8").strip()
    plain = decrypt_memory_base64(b64, key)
    if output_path:
        output_path.write_bytes(plain)
        typer.echo(f"已写入 {output_path}")
    else:
        sys.stdout.buffer.write(plain)


@sync_app.command("push")
def sync_push(
    agent: str = typer.Option(..., "--agent", help="Agent 名称"),
    schema: str = typer.Option(
        "v1",
        "--schema",
        help="memory_schema_version，对应 git 推送分支名",
    ),
    git_dir: Optional[Path] = typer.Option(
        None,
        "--git-dir",
        help="已 init 且配置 remote 的仓库；省略则只生成当前目录 mmem_payload.enc，不调用 MMEM sync API",
    ),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
    pull_rebase: bool = typer.Option(
        True,
        "--pull-rebase/--no-pull-rebase",
        help="推送前 git pull --rebase origin <schema>（首次远端无分支时会跳过）",
    ),
    skip_remote_check: bool = typer.Option(
        False,
        "--skip-remote-check",
        help="不校验 origin URL 是否包含 user_uuid 对应的 Gogs 用户名片段",
    ),
    pack_pnms: Optional[Path] = typer.Option(
        None,
        "--pack-pnms",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="将 PNMS 数据目录打成 tar.gz 后加密为 pnms_bundle.enc 一并提交",
    ),
) -> None:
    """
    有 --git-dir：begin-submit →（可选 pull --rebase）→ 写入加密 bundle → git commit/push → mark-completed。
    无 --git-dir：仅写入 ./mmem_payload.enc（本地准备，不占锁）。
    完整推送需 MMEM_USER_UUID、MMEM_PRIVATE_KEY_PATH、MindMemory 可达。
    """
    from mindmemory_client.api import MmemApiClient
    from mindmemory_client.keys import read_openssh_private_key_pem
    from mindmemory_client.memory_crypto import encrypt_memory_base64
    from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

    cfg = MindMemoryClientConfig()
    if base_url:
        cfg = cfg.model_copy(update={"base_url": base_url})
    if not cfg.private_key_path:
        typer.echo("需要 MMEM_PRIVATE_KEY_PATH", err=True)
        raise typer.Exit(1)

    pem = read_openssh_private_key_pem(Path(cfg.private_key_path))
    key = k_seed_bytes_from_private_key_openssh(pem)
    body = {
        "mmem_client_bundle": 1,
        "ts": int(time.time()),
        "agent_name": agent,
        "schema": schema,
    }
    b64 = encrypt_memory_base64(json.dumps(body, ensure_ascii=False).encode("utf-8"), key)

    work = Path(git_dir) if git_dir else Path.cwd()
    out_file = work / "mmem_payload.enc"

    if not git_dir:
        out_file.write_text(b64 + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out_file}")
        typer.echo("未使用 --git-dir：未调用 begin-submit。将本文件复制到仓库后手动同步，或再次运行并加 --git-dir。")
        return

    if not cfg.user_uuid:
        typer.echo("使用 --git-dir 同步需要 MMEM_USER_UUID", err=True)
        raise typer.Exit(1)

    lock_uuid = ""
    try:
        with MmemApiClient(cfg) as api:
            begin = api.begin_submit(cfg.user_uuid, agent, holder_info="mmem-cli push")
            lock_uuid = begin["lock_uuid"]
            typer.echo(f"begin-submit: lock_uuid={lock_uuid}")

        if not skip_remote_check:
            try:
                rurl = _git_remote_origin_url(git_dir)
                _validate_remote_url_for_user(rurl, cfg.user_uuid)
                typer.echo(f"origin 校验通过: {rurl[:80]}{'…' if len(rurl) > 80 else ''}")
            except (subprocess.CalledProcessError, ValueError) as e:
                typer.echo(f"远端校验失败: {e}", err=True)
                raise typer.Exit(1)

        if pull_rebase:
            ok, msg = _git_pull_rebase_origin(git_dir, schema)
            typer.echo(msg if ok else f"pull --rebase 失败: {msg}", err=not ok)
            if not ok:
                try:
                    with MmemApiClient(cfg) as api:
                        api.mark_completed(
                            cfg.user_uuid,
                            agent,
                            lock_uuid,
                            False,
                            None,
                            f"git pull --rebase: {msg}",
                            commit_for_payload="",
                        )
                except Exception:
                    pass
                raise typer.Exit(1)

        out_file.write_text(b64 + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out_file}")

        add_paths = ["mmem_payload.enc"]
        if pack_pnms:
            pnms_b64 = _pack_pnms_dir_to_encrypted_b64(pack_pnms, key)
            pnms_file = work / "pnms_bundle.enc"
            pnms_file.write_text(pnms_b64 + "\n", encoding="utf-8")
            typer.echo(f"已写入 {pnms_file}（来自 {pack_pnms}）")
            add_paths.append("pnms_bundle.enc")

        meta = json.dumps(
            {"memory_schema_version": schema, "client_version": "mindmemory-client"},
            ensure_ascii=False,
        )
        subprocess.run(
            ["git", "-C", str(git_dir), "add", *add_paths],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(git_dir),
                "commit",
                "-m",
                "mmem cli bundle",
                "-m",
                f"MMEM_META: {meta}",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(git_dir),
                "push",
                "origin",
                f"HEAD:refs/heads/{schema}",
            ],
            check=True,
        )
        commit_id = subprocess.check_output(
            ["git", "-C", str(git_dir), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        with MmemApiClient(cfg) as api:
            api.mark_completed(
                cfg.user_uuid,
                agent,
                lock_uuid,
                True,
                [commit_id],
                None,
                commit_for_payload=commit_id,
            )
        typer.echo(f"mark-completed: ok, commit_id={commit_id}")
    except subprocess.CalledProcessError as e:
        typer.echo(f"git 失败: {e}", err=True)
        if lock_uuid:
            try:
                with MmemApiClient(cfg) as api:
                    api.mark_completed(
                        cfg.user_uuid,
                        agent,
                        lock_uuid,
                        False,
                        None,
                        str(e),
                        commit_for_payload="",
                    )
            except Exception as e2:
                typer.echo(f"mark-completed(fail) 也失败: {e2}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"失败: {e}", err=True)
        if lock_uuid:
            try:
                with MmemApiClient(cfg) as api:
                    api.mark_completed(
                        cfg.user_uuid,
                        agent,
                        lock_uuid,
                        False,
                        None,
                        str(e),
                        commit_for_payload="",
                    )
            except Exception:
                pass
        raise typer.Exit(1)


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
