"""mmem：与 LLM 对话 + PNMS 记忆；默认本地 Ollama，可配置多 profile。"""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Optional

import typer

from mindmemory_client.client_state import resolve_mmem_config
from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.errors import MindMemoryAPIError
from mindmemory_client.llm_profiles import default_config_path, load_llm_profiles_from_toml, resolve_profile
from mindmemory_client.ollama_llm import build_ollama_llm, ollama_health

from mmem_cli.account import account_app
from mmem_cli.pnms_cmds import pnms_app

logger = logging.getLogger(__name__)

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

    cfg = resolve_mmem_config(base_url_override=base_url)
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

    from mindmemory_client.client_paths import client_config_dir, default_pnms_data_root
    from mindmemory_client.client_state import load_state
    from mindmemory_client.credential_source import credential_source

    src = credential_source()
    typer.echo(f"MMEM_CREDENTIAL_SOURCE: {src}（account=多账户目录 | env=环境变量 | none=无远端身份）")
    typer.echo(f"客户端配置目录: {client_config_dir()}")
    st = load_state()
    if st.current_account_uuid:
        typer.echo(f"当前账户（state）: {st.current_account_uuid}")
    else:
        typer.echo("当前账户（state）: 未选择（account 模式可用 mmem account login）")
    typer.echo(f"默认 PNMS 根（无 MMEM_PNMS_DATA_ROOT 时）: {default_pnms_data_root()}")

    if cfg.user_uuid:
        typer.echo(f"解析后 user_uuid: 已设置（长度 {len(cfg.user_uuid)}）")
    else:
        typer.echo("解析后 user_uuid: 未设置（仅本地 PNMS 时可忽略）")
    if cfg.private_key_path:
        typer.echo(f"解析后私钥: {cfg.private_key_path}")
    else:
        typer.echo("解析后私钥: 未设置（sync 需 account 登录或 MMEM_CREDENTIAL_SOURCE=env）")

    llm_cfg = load_llm_profiles_from_toml(config_path)
    prof = resolve_profile(llm_cfg, None)
    typer.echo(f"配置文件: {config_path or default_config_path()}（存在则已加载多模型）")
    typer.echo(f"当前默认 LLM profile: {llm_cfg.default_profile} → {prof.ollama_model} @ {prof.ollama_base_url}")

    from mindmemory_client.env_loader import get_env

    _lv = (get_env("MMEM_LOG_LEVEL") or "").strip() or "INFO"
    typer.echo(f"MMEM_LOG_LEVEL: {_lv}（未设置时按 INFO）")
    _lf = get_env("MMEM_LOG_FILE")
    typer.echo(f"MMEM_LOG_FILE: {_lf or '（未设置，仅 stderr）'}")
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

    cfg = resolve_mmem_config(base_url_override=base_url)
    cfg = cfg.model_copy(update={"agent_name": agent})

    uid = cfg.user_uuid or "local-dev-user"
    bridge = PnmsMemoryBridge(cfg.pnms_data_root, uid, agent)
    session = ChatMemorySession(bridge)
    llm_fn = _build_llm_callback(llm_mode, profile, ollama_url, model, config_path)
    logger.info("mmem chat agent=%s llm_mode=%s user=%s", agent, llm_mode, uid)

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

memory_app = typer.Typer(help="PNMS 记忆（合并等）")


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


def _git_fetch_origin(git_dir: Path) -> None:
    subprocess.run(
        ["git", "-C", str(git_dir), "fetch", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_compare_with_remote(git_dir: Path, schema: str) -> str:
    """
    在 ``git fetch origin`` 之后比较 HEAD 与 origin/<schema>。
    返回: no_remote_branch | up_to_date | ahead | behind | diverged
    """
    ref = f"origin/{schema}"
    r = subprocess.run(
        ["git", "-C", str(git_dir), "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return "no_remote_branch"

    head = subprocess.check_output(
        ["git", "-C", str(git_dir), "rev-parse", "HEAD"], text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "-C", str(git_dir), "rev-parse", ref], text=True
    ).strip()
    if head == remote:
        return "up_to_date"

    if (
        subprocess.run(
            ["git", "-C", str(git_dir), "merge-base", "--is-ancestor", head, remote],
            capture_output=True,
        ).returncode
        == 0
    ):
        return "behind"
    if (
        subprocess.run(
            ["git", "-C", str(git_dir), "merge-base", "--is-ancestor", remote, head],
            capture_output=True,
        ).returncode
        == 0
    ):
        return "ahead"
    return "diverged"


def _resolve_pnms_dir_for_push(
    cfg: MindMemoryClientConfig, agent: str, pack_pnms: Optional[Path]
) -> Path:
    from mindmemory_client.pnms_bridge import resolve_pnms_data_dir

    if pack_pnms is not None:
        return pack_pnms
    if not cfg.user_uuid:
        typer.echo(
            "请指定 --pack-pnms，或在 account 模式下 mmem account login；"
            f"或 MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_USER_UUID 以使用默认目录 "
            f"（{cfg.pnms_data_root}/<user>/<agent>/）",
            err=True,
        )
        raise typer.Exit(1)
    return resolve_pnms_data_dir(cfg.pnms_data_root, cfg.user_uuid, agent)


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
        help="已 init 且配置 remote 的仓库；省略则只写入当前目录 pnms_bundle.enc，不调用 MMEM sync API",
    ),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
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
        help="要打包的 PNMS 目录；默认使用解析到的 user_uuid 与 MMEM_PNMS_DATA_ROOT/<user>/<agent>/",
    ),
) -> None:
    """
    仅推送 **PNMS 目录** 经 tar.gz + AES-GCM（K_seed）后的 ``pnms_bundle.enc``，不再生成占位 ``mmem_payload.enc``。

    有 ``--git-dir``：先 ``git fetch`` 并比较与 ``origin/<schema>``；若远端更新或分叉则**不占用同步锁**并退出，
    需先执行 ``mmem memory merge`` 完成 Git 对齐与（未来）PNMS 合并后再推送。

    无 ``--git-dir``：仅生成本地 ``./pnms_bundle.enc``，不占锁。
    """
    from mindmemory_client.api import MmemApiClient
    from mindmemory_client.keys import read_openssh_private_key_pem
    from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

    cfg = resolve_mmem_config(base_url_override=base_url)
    if not cfg.private_key_path:
        typer.echo(
            "需要私钥：MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_PRIVATE_KEY_PATH，"
            "或 MMEM_CREDENTIAL_SOURCE=account（默认）且 mmem account login。",
            err=True,
        )
        raise typer.Exit(1)

    pem = read_openssh_private_key_pem(Path(cfg.private_key_path))
    key = k_seed_bytes_from_private_key_openssh(pem)
    pnms_src = _resolve_pnms_dir_for_push(cfg, agent, pack_pnms)
    pnms_src.mkdir(parents=True, exist_ok=True)
    bundle_b64 = _pack_pnms_dir_to_encrypted_b64(pnms_src, key)

    work = Path(git_dir) if git_dir else Path.cwd()
    out_file = work / "pnms_bundle.enc"

    if not git_dir:
        out_file.write_text(bundle_b64 + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out_file}（PNMS 来源: {pnms_src}）")
        typer.echo("未使用 --git-dir：未调用 begin-submit。复制到仓库后执行 mmem sync push --git-dir … 完成上传。")
        return

    if not cfg.user_uuid:
        typer.echo(
            "使用 --git-dir 需要 user_uuid：account 模式请 mmem account login；"
            "或 MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_USER_UUID。",
            err=True,
        )
        raise typer.Exit(1)

    if not skip_remote_check:
        try:
            rurl = _git_remote_origin_url(git_dir)
            _validate_remote_url_for_user(rurl, cfg.user_uuid)
            typer.echo(f"origin 校验通过: {rurl[:80]}{'…' if len(rurl) > 80 else ''}")
        except (subprocess.CalledProcessError, ValueError) as e:
            typer.echo(f"远端校验失败: {e}", err=True)
            raise typer.Exit(1)

    try:
        _git_fetch_origin(git_dir)
    except subprocess.CalledProcessError as e:
        typer.echo(f"git fetch 失败: {e}", err=True)
        raise typer.Exit(1)

    rel = _git_compare_with_remote(git_dir, schema)
    typer.echo(f"与 origin/{schema} 比较: {rel}")
    if rel in ("behind", "diverged"):
        typer.echo(
            "远端已有较新或分叉提交，已中止推送（未占用同步锁）。\n"
            "请先在同一仓库执行：\n"
            f"  mmem memory merge --git-dir {git_dir} --schema {schema}\n"
            "手动处理冲突并（未来由 PNMS 完成）合并本地 PNMS 数据后，再执行 mmem sync push。",
            err=True,
        )
        raise typer.Exit(2)

    lock_uuid = ""
    try:
        with MmemApiClient(cfg) as api:
            begin = api.begin_submit(cfg.user_uuid, agent, holder_info="mmem-cli push")
            lock_uuid = begin["lock_uuid"]
            typer.echo(f"begin-submit: lock_uuid={lock_uuid}")

        out_file.write_text(bundle_b64 + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out_file}（PNMS 来源: {pnms_src}）")

        meta = json.dumps(
            {
                "memory_schema_version": schema,
                "client_version": "mindmemory-client",
                "bundle": "pnms_bundle.enc",
            },
            ensure_ascii=False,
        )
        subprocess.run(
            ["git", "-C", str(git_dir), "add", "pnms_bundle.enc"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(git_dir),
                "commit",
                "-m",
                "mmem: sync PNMS bundle",
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


@memory_app.command("merge")
def memory_merge(
    git_dir: Path = typer.Option(
        ...,
        "--git-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="已配置 origin 的本地 Git 仓库",
    ),
    schema: str = typer.Option(
        "v1",
        "--schema",
        help="与 mmem sync push 一致的分支名（memory_schema_version）",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅打印将执行的命令，不修改仓库"),
) -> None:
    """
    拉取远端并尝试 ``git pull --rebase origin <schema>``，使本地与远端提交历史对齐。

    **PNMS 语义合并**（权重/图/槽等）尚未在库内实现：当前仅处理 Git 层。
    合并后请将远端 ``pnms_bundle.enc`` 解密并与本地 PNMS 目录协调（或等待 PNMS 提供合并 API）。
    """
    if dry_run:
        typer.echo(f"将执行: git -C {git_dir} fetch origin")
        typer.echo(f"将执行: git -C {git_dir} pull --rebase origin {schema}")
        return
    try:
        subprocess.run(
            ["git", "-C", str(git_dir), "fetch", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        typer.echo(f"git fetch 失败: {e}", err=True)
        raise typer.Exit(1)
    pr = subprocess.run(
        ["git", "-C", str(git_dir), "pull", "--rebase", "origin", schema],
        capture_output=True,
        text=True,
    )
    if pr.returncode != 0:
        typer.echo((pr.stderr or "") + (pr.stdout or ""), err=True)
        typer.echo(
            "pull --rebase 失败。请手动解决冲突后再次执行本命令，再运行 mmem sync push。",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo("Git 已与远端对齐。请确认 PNMS 数据与 pnms_bundle.enc 的合并策略后再执行 mmem sync push。")


@sync_app.command("ping")
def sync_ping(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """调用 GET /me 与 GET /agents（需解析到 user_uuid）。"""
    cfg = resolve_mmem_config(base_url_override=base_url)
    if not cfg.user_uuid:
        typer.echo(
            "需要 user_uuid：account 模式请 mmem account login；"
            "或 MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_USER_UUID。",
            err=True,
        )
        raise typer.Exit(1)
    from mindmemory_client.api import MmemApiClient

    with MmemApiClient(cfg) as api:
        me = api.get_me(cfg.user_uuid)
        typer.echo(f"me: {me}")
        agents = api.list_agents(cfg.user_uuid)
        typer.echo(f"agents: {agents}")


app.add_typer(sync_app, name="sync")
app.add_typer(memory_app, name="memory")
app.add_typer(account_app, name="account")
app.add_typer(pnms_app, name="pnms")


def main() -> None:
    from mindmemory_client.logging_config import configure_client_logging

    configure_client_logging()
    app()


if __name__ == "__main__":
    main()
