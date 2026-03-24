"""mmem：MindMemory 官方示例 CLI（仅依赖 ``mindmemory_client``）。

对话、记忆 bundle、同步等一律通过库内 API（如 ``PnmsMemoryBridge``、``import_encrypted_bundle_to_agent_checkpoint``）；
**不**在 CLI 中 ``import pnms``；底层引擎由 ``mindmemory_client.pnms_bridge`` 集中加载。默认本地 Ollama，可配置多 profile。
"""

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
from mindmemory_client.llm_profiles import default_config_path, effective_ollama_url, load_llm_profiles_from_toml, resolve_profile
from mindmemory_client.memory_schema import resolve_memory_schema_version
from mindmemory_client.ollama_llm import build_ollama_llm, ollama_health

from mmem_cli.account import account_app
from mmem_cli.agent_app import agent_app
from mmem_cli.cli_auth import require_authenticated_user
from mmem_cli.models_app import models_app
from mmem_cli.pnms_cmds import pnms_app

logger = logging.getLogger(__name__)

app = typer.Typer(
    no_args_is_help=True,
    help="MindMemory 示例客户端（mindmemory_client：记忆引擎 + MMEM API）；默认 Ollama",
)


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
    """检查依赖、记忆引擎是否可被 mindmemory_client 加载、MindMemory /health、Ollama /api/tags。"""
    typer.echo("Python:", nl=False)
    typer.echo(f" {sys.version.split()[0]}")
    from mindmemory_client.pnms_bridge import is_memory_engine_available

    if is_memory_engine_available():
        typer.echo("记忆引擎 (pnms): 已安装")
    else:
        typer.echo("记忆引擎 (pnms): 未安装（请先 pip install -e ../pnms）", err=True)

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

    from mindmemory_client.client_paths import client_config_dir, client_data_dir
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
    typer.echo(f"数据目录（pnms_data_root 默认与此一致）: {client_data_dir()}")
    typer.echo("checkpoint 目录: accounts/<user_uuid>/agents/<agent>/pnms（由 mindmemory_client 读写，CLI 不直接 import pnms）")
    typer.echo(f"默认 Agent（mmem chat / sync 等省略 --agent 时）: {cfg.agent_name}")
    if st.current_agent_name:
        typer.echo(f"  （state.current_agent_name={st.current_agent_name!r}；可用 mmem agent list / use）")
    else:
        typer.echo("  （未设置 current_agent_name，与内置默认 BT-7274 一致；可用 mmem agent use）")

    if cfg.user_uuid:
        typer.echo(f"解析后 user_uuid: 已设置（长度 {len(cfg.user_uuid)}）")
    else:
        typer.echo("解析后 user_uuid: 未设置（对话与同步需先 mmem account login）")
    if cfg.private_key_path:
        typer.echo(f"解析后私钥: {cfg.private_key_path}")
    else:
        typer.echo("解析后私钥: 未设置（sync 需 account 登录或 MMEM_CREDENTIAL_SOURCE=env）")

    llm_cfg = load_llm_profiles_from_toml(config_path)
    prof = resolve_profile(llm_cfg, None)
    typer.echo(f"配置文件: {config_path or default_config_path()}（存在则已加载多模型）")
    typer.echo(
        f"当前默认 LLM profile: {llm_cfg.default_profile} → {prof.ollama_model} @ {effective_ollama_url(prof)} "
        f"(target={prof.target}, token={'已配置' if prof.api_token else '无'})"
    )
    typer.echo(
        f"默认 memory_schema_version（sync push / memory merge）: {resolve_memory_schema_version(None)} "
        f"（与已安装记忆引擎的格式版本一致；可用 --schema 覆盖）"
    )

    from mindmemory_client.env_loader import get_env

    _lv = (get_env("MMEM_LOG_LEVEL") or "").strip() or "INFO"
    typer.echo(f"MMEM_LOG_LEVEL: {_lv}（未设置时按 INFO）")
    _lf = get_env("MMEM_LOG_FILE")
    typer.echo(f"MMEM_LOG_FILE: {_lf or '（未设置，仅 stderr）'}")
    try:
        _oh: dict[str, str] = {}
        if prof.api_token and str(prof.api_token).strip():
            _oh["Authorization"] = f"Bearer {prof.api_token.strip()}"
        tags = ollama_health(effective_ollama_url(prof), headers=_oh)
        models = tags.get("models") or []
        names = [m.get("name", "?") for m in models[:12]]
        extra = f" …共 {len(models)} 个" if len(models) > 12 else ""
        typer.echo(f"Ollama /api/tags: OK（示例: {', '.join(names)}{extra}）")
    except Exception as e:
        typer.echo(f"Ollama: 不可用（{e}）", err=True)


@app.command()
def chat(
    message: Optional[str] = typer.Option(None, "-m", "--message", help="单次提问后退出"),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent 名称；省略则使用 mmem agent use 所设或默认 BT-7274",
    ),
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
    """交互对话或 -m 单次；每轮经 ``ChatMemorySession`` / ``PnmsMemoryBridge`` 更新记忆并落盘。默认走本地 Ollama。"""
    try:
        from mindmemory_client.pnms_bridge import PnmsMemoryBridge
        from mindmemory_client.session import ChatMemorySession
    except ImportError as e:
        typer.echo(f"导入失败: {e}（需可安装 ``pip install -e ../pnms`` 供 mindmemory_client 加载）", err=True)
        raise typer.Exit(1)

    cfg = resolve_mmem_config(base_url_override=base_url, agent_name_override=agent)
    require_authenticated_user(cfg)
    agent = cfg.agent_name

    uid = cfg.user_uuid
    assert uid is not None
    from mindmemory_client.agent_workspace import resolve_pnms_dir_for_user_agent

    pnms_ckpt = resolve_pnms_dir_for_user_agent(cfg, uid, agent)
    bridge = PnmsMemoryBridge(cfg.pnms_data_root, uid, agent, checkpoint_dir=pnms_ckpt)
    session = ChatMemorySession(bridge)
    llm_fn = _build_llm_callback(llm_mode, profile, ollama_url, model, config_path)
    logger.info("mmem chat agent=%s llm_mode=%s user=%s", agent, llm_mode, uid)

    if llm_mode == "ollama":
        p = resolve_profile(load_llm_profiles_from_toml(config_path), profile, ollama_url_override=ollama_url, ollama_model_override=model)
        typer.echo(
            f"[LLM] profile={profile!r} model={p.ollama_model} @ {effective_ollama_url(p)} "
            f"(target={p.target}, auth={'yes' if p.api_token else 'no'})"
        )

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

memory_app = typer.Typer(help="记忆 Git 对齐与加密 bundle 导入（mindmemory_client.memory_bundle）")


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
    from mindmemory_client.agent_workspace import resolve_pnms_dir_for_user_agent

    if pack_pnms is not None:
        return pack_pnms
    if not cfg.user_uuid:
        typer.echo(
            "请指定 --pack-pnms，或先登录（mmem account login）"
            " / 配置 MMEM_CREDENTIAL_SOURCE=env 与 MMEM_USER_UUID；"
            "默认 PNMS 目录为 accounts/<user_uuid>/agents/<agent>/pnms。",
            err=True,
        )
        raise typer.Exit(1)
    return resolve_pnms_dir_for_user_agent(cfg, cfg.user_uuid, agent)


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
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent 名称；省略则使用 mmem agent use 所设或默认 BT-7274",
    ),
    schema: Optional[str] = typer.Option(
        None,
        "--schema",
        help="memory_schema_version / git 分支名；默认与 PNMS get_memory_format_version() 一致",
    ),
    git_dir: Optional[Path] = typer.Option(
        None,
        "--git-dir",
        help="已 init 且配置 origin 的记忆仓库；省略时若已 mmem agent init 则使用该 Agent 的 repo/",
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
        help="要打包的 PNMS 目录；默认使用 accounts/<user>/agents/<agent>/pnms",
    ),
    sync_extras: bool = typer.Option(
        False,
        "--sync-extras",
        help="若存在 workspace/.mmem-sync-manifest.json 则打包为 mmem/bundles/extras.enc 并与 pnms_bundle.enc 同批提交",
    ),
) -> None:
    """
    仅推送 **PNMS 目录** 经 tar.gz + AES-GCM（K_seed）后的 ``pnms_bundle.enc``，不再生成占位 ``mmem_payload.enc``。

    若解析到记忆仓库路径（``--git-dir`` 或 ``mmem agent init`` 后的 ``.../agents/<agent>/repo``）：
    先 ``git fetch`` 并比较与 ``origin/<schema>``；若远端更新或分叉则**不占用同步锁**并退出，
    需先执行 ``mmem memory merge`` 完成 Git 对齐后再推送。

    若既无 ``--git-dir`` 也未初始化 Agent 工作区：仅生成本地 ``./pnms_bundle.enc``，不占锁。

    ``--sync-extras`` 仅在已解析到记忆仓库且存在有效清单时写入 ``mmem/bundles/extras.enc``（见 docs/memory-repo-extended-layout.md）。
    """
    from mindmemory_client.api import MmemApiClient
    from mindmemory_client.keys import read_openssh_private_key_pem
    from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

    schema = resolve_memory_schema_version(schema)
    cfg = resolve_mmem_config(base_url_override=base_url, agent_name_override=agent)
    require_authenticated_user(cfg)
    agent = cfg.agent_name
    if not cfg.private_key_path:
        typer.echo(
            "需要私钥：MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_PRIVATE_KEY_PATH，"
            "或 MMEM_CREDENTIAL_SOURCE=account（默认）且 mmem account login。",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"memory_schema_version（分支）: {schema}")

    pem = read_openssh_private_key_pem(Path(cfg.private_key_path))
    key = k_seed_bytes_from_private_key_openssh(pem)
    pnms_src = _resolve_pnms_dir_for_push(cfg, agent, pack_pnms)
    pnms_src.mkdir(parents=True, exist_ok=True)
    bundle_b64 = _pack_pnms_dir_to_encrypted_b64(pnms_src, key)

    resolved_git: Optional[Path] = Path(git_dir) if git_dir else None
    if resolved_git is None and cfg.user_uuid:
        from mindmemory_client.agent_workspace import resolve_git_dir_for_sync

        cand = resolve_git_dir_for_sync(cfg, agent)
        if cand is not None and (cand / ".git").exists():
            resolved_git = cand
            typer.echo(f"使用 Agent 工作区记忆仓库: {resolved_git.resolve()}")

    work = resolved_git if resolved_git is not None else Path.cwd()
    out_file = work / "pnms_bundle.enc"

    if git_dir is None and resolved_git is None:
        out_file.write_text(bundle_b64 + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out_file}（PNMS 来源: {pnms_src}）")
        if sync_extras:
            typer.echo(
                "未配置记忆仓库：已跳过 --sync-extras（需 Agent 工作区 repo/ 才能写入 mmem/bundles/extras.enc）。",
                err=True,
            )
        typer.echo(
            "未配置记忆仓库：未调用 begin-submit。"
            "可执行 mmem agent init <agent> 后重试，或手动指定 --git-dir。"
        )
        return

    git_repo = work.resolve()

    if not cfg.user_uuid:
        typer.echo(
            "使用 --git-dir 需要 user_uuid：account 模式请 mmem account login；"
            "或 MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_USER_UUID。",
            err=True,
        )
        raise typer.Exit(1)

    if not skip_remote_check:
        try:
            rurl = _git_remote_origin_url(git_repo)
            _validate_remote_url_for_user(rurl, cfg.user_uuid)
            typer.echo(f"origin 校验通过: {rurl[:80]}{'…' if len(rurl) > 80 else ''}")
        except (subprocess.CalledProcessError, ValueError) as e:
            typer.echo(f"远端校验失败: {e}", err=True)
            raise typer.Exit(1)

    try:
        _git_fetch_origin(git_repo)
    except subprocess.CalledProcessError as e:
        typer.echo(f"git fetch 失败: {e}", err=True)
        raise typer.Exit(1)

    rel = _git_compare_with_remote(git_repo, schema)
    typer.echo(f"与 origin/{schema} 比较: {rel}")
    if rel in ("behind", "diverged"):
        typer.echo(
            "远端已有较新或分叉提交，已中止推送（未占用同步锁）。\n"
            "请先在同一仓库执行：\n"
            f"  mmem memory merge --git-dir {git_repo} --schema {schema}\n"
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

        extras_rel = "mmem/bundles/extras.enc"
        extras_path = git_repo / extras_rel
        extras_done = False
        if sync_extras and cfg.user_uuid:
            from mindmemory_client.agent_workspace import resolve_workspace_dir_for_user_agent
            from mindmemory_client.sync_manifest import MANIFEST_FILENAME, SyncManifestError
            from mindmemory_client.workspace_extras import pack_workspace_extras_from_manifest_file

            ws_dir = resolve_workspace_dir_for_user_agent(cfg.user_uuid, agent)
            man = ws_dir / MANIFEST_FILENAME
            if man.is_file():
                try:
                    extras_b64 = pack_workspace_extras_from_manifest_file(man, ws_dir, key)
                    extras_path.parent.mkdir(parents=True, exist_ok=True)
                    extras_path.write_text(extras_b64 + "\n", encoding="utf-8")
                    extras_done = True
                    typer.echo(f"已写入 {extras_path}（来源 workspace 清单）")
                except SyncManifestError as e:
                    typer.echo(f"extras 打包失败: {e}", err=True)
                    raise typer.Exit(1)
            else:
                typer.echo(f"--sync-extras：未找到 {man}，跳过 extras。")

        meta_obj: dict[str, object] = {
            "memory_schema_version": schema,
            "client_version": "mindmemory-client",
            "bundle": "pnms_bundle.enc",
        }
        if extras_done:
            meta_obj["extras_bundle"] = extras_rel
        meta = json.dumps(meta_obj, ensure_ascii=False)
        subprocess.run(
            ["git", "-C", str(git_repo), "add", "pnms_bundle.enc"],
            check=True,
        )
        if extras_done:
            subprocess.run(
                ["git", "-C", str(git_repo), "add", extras_rel],
                check=True,
            )
        commit_msg = (
            "mmem: sync PNMS + workspace extras bundles"
            if extras_done
            else "mmem: sync PNMS bundle"
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(git_repo),
                "commit",
                "-m",
                commit_msg,
                "-m",
                f"MMEM_META: {meta}",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(git_repo),
                "push",
                "origin",
                f"HEAD:refs/heads/{schema}",
            ],
            check=True,
        )
        commit_id = subprocess.check_output(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
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


@memory_app.command("import-bundle")
def memory_import_bundle(
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="与 mmem agent use / chat 一致；省略则用 state 或默认 BT-7274",
    ),
    git_dir: Optional[Path] = typer.Option(
        None,
        "--git-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="含 pnms_bundle.enc 的记忆仓库；省略时尝试 Agent 工作区 repo/",
    ),
    bundle: Optional[Path] = typer.Option(
        None,
        "--bundle",
        exists=True,
        readable=True,
        help="密文文件路径；默认 <git-dir>/pnms_bundle.enc（仅指定 --bundle 时可省略 --git-dir）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="仅打印 bundle 路径与目标 pnms 目录；不写盘、不调用 mindmemory_client 记忆引擎",
    ),
    import_extras: bool = typer.Option(
        False,
        "--import-extras",
        help="合并 PNMS bundle 后（或配合 --extras-only）从仓库内 mmem/bundles/extras.enc 解压到 workspace/",
    ),
    extras_only: bool = typer.Option(
        False,
        "--extras-only",
        help="仅解压 extras.enc，不导入 pnms_bundle.enc（需 --git-dir 或已初始化的 Agent repo）",
    ),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """
    解密 ``pnms_bundle.enc`` 至临时目录，经 ``mindmemory_client.memory_bundle.import_encrypted_bundle_to_agent_checkpoint``
    合并进当前 Agent 的 ``…/agents/<agent>/pnms`` 并落盘（内部使用 ``PnmsMemoryBridge.merge_external_checkpoint`` + ``persist_checkpoint``）。
    底层合并语义见已安装的 ``pnms`` 包文档 ``docs/pnms_api.md``。

    ``--import-extras`` / ``--extras-only`` 见 docs/memory-repo-extended-layout.md。
    """
    cfg = resolve_mmem_config(base_url_override=base_url, agent_name_override=agent)
    require_authenticated_user(cfg)
    agent = cfg.agent_name
    uid = cfg.user_uuid
    assert uid is not None
    if not cfg.private_key_path:
        typer.echo(
            "需要私钥以派生 K_seed：account 模式请 mmem account login；"
            "或 MMEM_CREDENTIAL_SOURCE=env 且设置 MMEM_PRIVATE_KEY_PATH。",
            err=True,
        )
        raise typer.Exit(1)

    from mindmemory_client.agent_workspace import resolve_git_dir_for_sync, resolve_pnms_dir_for_user_agent

    if extras_only and import_extras is False:
        import_extras = True

    repo: Path | None = Path(git_dir) if git_dir else None
    if repo is None:
        cand = resolve_git_dir_for_sync(cfg, agent)
        if cand is not None and (cand / ".git").exists():
            repo = cand

    if bundle is not None:
        bundle_path = bundle
    elif repo is not None:
        bundle_path = repo / "pnms_bundle.enc"
    else:
        bundle_path = None  # type: ignore[assignment]

    if extras_only:
        if repo is None:
            typer.echo("--extras-only 需要 --git-dir 或已 mmem agent init 的记忆仓库。", err=True)
            raise typer.Exit(1)
    elif bundle_path is None or not bundle_path.is_file():
        typer.echo("请指定 --bundle 或 --git-dir（或先 mmem agent init 并配置记忆仓库）。", err=True)
        raise typer.Exit(1)

    dest = resolve_pnms_dir_for_user_agent(cfg, uid, agent)
    if dry_run:
        typer.echo(f"目标 checkpoint 目录: {dest}")
        if bundle_path is not None:
            typer.echo(f"bundle 文件: {bundle_path}")
        if import_extras and repo is not None:
            typer.echo(f"extras 文件: {repo / 'mmem/bundles/extras.enc'}")
        return

    from mindmemory_client.keys import read_openssh_private_key_pem
    from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

    pem = read_openssh_private_key_pem(Path(cfg.private_key_path))
    key = k_seed_bytes_from_private_key_openssh(pem)

    if not extras_only:
        from mindmemory_client.memory_bundle import (
            format_memory_engine_error,
            import_encrypted_bundle_to_agent_checkpoint,
        )
        from mindmemory_client.memory_errors import MemoryEngineError

        assert bundle_path is not None
        try:
            meta = import_encrypted_bundle_to_agent_checkpoint(
                bundle_path=bundle_path,
                key=key,
                dest_pnms_dir=dest,
                cfg=cfg,
                user_uuid=uid,
                agent_name=agent,
            )
        except MemoryEngineError as e:
            typer.echo(format_memory_engine_error(e), err=True)
            raise typer.Exit(1)
        typer.echo(f"已与 bundle 融合并保存 checkpoint → {dest}")
        typer.echo(f"槽数量: {meta.get('num_slots')}")

    if import_extras:
        assert repo is not None
        extras_path = repo / "mmem/bundles/extras.enc"
        if not extras_path.is_file():
            typer.echo(f"未找到 {extras_path}，跳过 extras。", err=True)
            if extras_only:
                raise typer.Exit(1)
        else:
            from mindmemory_client.agent_workspace import resolve_workspace_dir_for_user_agent
            from mindmemory_client.workspace_extras import decrypt_extras_bundle_file_to_workspace

            ws = resolve_workspace_dir_for_user_agent(uid, agent)
            xmeta = decrypt_extras_bundle_file_to_workspace(extras_path, ws, key)
            typer.echo(f"已解压 extras → {ws}（写入 {len(xmeta.get('written', []))} 个文件）")


@memory_app.command("merge")
def memory_merge(
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="与 mmem agent use / chat 一致；省略则用 state 或默认 BT-7274",
    ),
    git_dir: Optional[Path] = typer.Option(
        None,
        "--git-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="已配置 origin 的本地记忆仓库；省略时尝试 Agent 工作区 repo/",
    ),
    schema: Optional[str] = typer.Option(
        None,
        "--schema",
        help="与 mmem sync push 一致；默认 PNMS get_memory_format_version()",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅打印将执行的命令，不修改仓库"),
    import_bundle: bool = typer.Option(
        False,
        "--import-bundle",
        help="pull 成功后解密 pnms_bundle.enc 并调用库 API 合并到本 Agent pnms/（需私钥）",
    ),
    import_extras: bool = typer.Option(
        False,
        "--import-extras",
        help="pull 成功后解密 mmem/bundles/extras.enc 并解压到本 Agent workspace/（需私钥）",
    ),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """
    拉取远端并尝试 ``git pull --rebase origin <schema>``，使本地与远端提交历史对齐。

    可选 ``--import-bundle``：Git 对齐后调用 ``import_encrypted_bundle_to_agent_checkpoint``（与 ``mmem memory import-bundle`` 相同）。
    ``--import-extras``：对齐后解压 extras.enc（见 docs/memory-repo-extended-layout.md）。
    """
    from mindmemory_client.agent_workspace import resolve_git_dir_for_sync

    schema = resolve_memory_schema_version(schema)
    cfg = resolve_mmem_config(base_url_override=base_url, agent_name_override=agent)
    require_authenticated_user(cfg)
    agent = cfg.agent_name
    repo = git_dir
    if repo is None and cfg.user_uuid:
        cand = resolve_git_dir_for_sync(cfg, agent)
        if cand is not None and (cand / ".git").exists():
            repo = cand
    if repo is None:
        typer.echo("请指定 --git-dir，或先 mmem agent init 并 clone 记忆仓库。", err=True)
        raise typer.Exit(1)
    git_dir = repo

    if dry_run:
        typer.echo(f"将执行: git -C {git_dir} fetch origin")
        typer.echo(f"将执行: git -C {git_dir} pull --rebase origin {schema}")
        if import_bundle:
            typer.echo(
                f"将执行: 解密 {git_dir}/pnms_bundle.enc 并经 mindmemory_client.memory_bundle 合并到本 Agent pnms/"
            )
        if import_extras:
            typer.echo(
                f"将执行: 解密 {git_dir}/mmem/bundles/extras.enc 并解压到本 Agent workspace/"
            )
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
    typer.echo("Git 已与远端对齐。")
    if import_bundle:
        if not cfg.private_key_path:
            typer.echo(
                "--import-bundle 需要私钥：请 mmem account login 或设置 MMEM_PRIVATE_KEY_PATH。",
                err=True,
            )
            raise typer.Exit(1)
        uid = cfg.user_uuid
        assert uid is not None
        bundle_path = git_dir / "pnms_bundle.enc"
        if not bundle_path.is_file():
            typer.echo(f"未找到 {bundle_path}，无法导入。", err=True)
            raise typer.Exit(1)
        from mindmemory_client.agent_workspace import resolve_pnms_dir_for_user_agent
        from mindmemory_client.keys import read_openssh_private_key_pem
        from mindmemory_client.memory_bundle import (
            format_memory_engine_error,
            import_encrypted_bundle_to_agent_checkpoint,
        )
        from mindmemory_client.memory_errors import MemoryEngineError
        from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh

        dest = resolve_pnms_dir_for_user_agent(cfg, uid, agent)
        pem = read_openssh_private_key_pem(Path(cfg.private_key_path))
        key = k_seed_bytes_from_private_key_openssh(pem)
        try:
            meta = import_encrypted_bundle_to_agent_checkpoint(
                bundle_path=bundle_path,
                key=key,
                dest_pnms_dir=dest,
                cfg=cfg,
                user_uuid=uid,
                agent_name=agent,
            )
        except MemoryEngineError as e:
            typer.echo(format_memory_engine_error(e), err=True)
            raise typer.Exit(1)
        typer.echo(f"已与 bundle 融合并保存 checkpoint → {dest}（槽数量: {meta.get('num_slots')}）")
    else:
        typer.echo(
            "可执行 mmem memory import-bundle：经 mindmemory_client 合并 bundle 到本地 pnms/ 后再 mmem sync push。"
        )

    if import_extras:
        if not cfg.private_key_path:
            typer.echo(
                "--import-extras 需要私钥：请 mmem account login 或设置 MMEM_PRIVATE_KEY_PATH。",
                err=True,
            )
            raise typer.Exit(1)
        uid = cfg.user_uuid
        assert uid is not None
        extras_path = git_dir / "mmem/bundles/extras.enc"
        if not extras_path.is_file():
            typer.echo(f"未找到 {extras_path}，跳过 extras。", err=True)
        else:
            from mindmemory_client.agent_workspace import resolve_workspace_dir_for_user_agent
            from mindmemory_client.keys import read_openssh_private_key_pem
            from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh
            from mindmemory_client.workspace_extras import decrypt_extras_bundle_file_to_workspace

            ws = resolve_workspace_dir_for_user_agent(uid, agent)
            pem = read_openssh_private_key_pem(Path(cfg.private_key_path))
            key = k_seed_bytes_from_private_key_openssh(pem)
            xmeta = decrypt_extras_bundle_file_to_workspace(extras_path, ws, key)
            typer.echo(f"已解压 extras → {ws}（写入 {len(xmeta.get('written', []))} 个文件）")


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
app.add_typer(agent_app, name="agent")
app.add_typer(models_app, name="models")
app.add_typer(pnms_app, name="pnms")


def main() -> None:
    from mindmemory_client.logging_config import configure_client_logging

    configure_client_logging()
    app()


if __name__ == "__main__":
    main()
