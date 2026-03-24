"""
Agent 工作区：账号目录下 ``accounts/<user_uuid>/agents/<agent>/``，
含 PNMS 数据（``pnms/``）与记忆 Git 仓库（``repo/``）。

设计文档另约定可选同级 ``workspace/``（Claw/CLI 源文件池）及运行时清单
``workspace/.mmem-sync-manifest.json``（不入 ``repo``），见 ``docs/memory-repo-extended-layout.md``。

与 MindMemory 约定一致：远端仓库在**首次 begin-submit** 时由服务端创建；
本地通过 ``ensure_agent_registered_on_server`` 触发注册后，再 ``git clone`` SSH 地址。
OpenClaw 等宿主应把当前 Agent 名映射为 ``agent_name``，与此处相同。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from mindmemory_client.client_paths import account_dir
from mindmemory_client.config import DEFAULT_AGENT_NAME, MindMemoryClientConfig
from mindmemory_client.env_loader import get_env


def _safe_segment(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return s[:200] if s else "default"


def gogs_username(user_uuid: str) -> str:
    """与 MindMemory / Gogs 一致：去掉 user_uuid 中的 ``-``。"""
    return user_uuid.replace("-", "")


def memory_repo_ssh_url(user_uuid: str, agent_name: str, *, ssh_host: str) -> str:
    """
    Gogs SCP 风格地址：``git@{host}:{gogs_user}/{agent}.git``。
    ``ssh_host`` 为纯主机名（不含 ``git@``），如 ``gogs.example.com``。
    """
    owner = gogs_username(user_uuid)
    seg = _safe_segment(agent_name)
    return f"git@{ssh_host}:{owner}/{seg}.git"


def agent_workspace_dir(user_uuid: str, agent_name: str) -> Path:
    """``~/.mindmemory/accounts/<uuid>/agents/<agent>/``"""
    return account_dir(user_uuid) / "agents" / _safe_segment(agent_name)


def agent_pnms_dir(user_uuid: str, agent_name: str) -> Path:
    return agent_workspace_dir(user_uuid, agent_name) / "pnms"


def agent_git_dir(user_uuid: str, agent_name: str) -> Path:
    """记忆仓库 clone 目录（含 ``.git``）。"""
    return agent_workspace_dir(user_uuid, agent_name) / "repo"


def resolve_workspace_dir_for_user_agent(user_uuid: str, agent_name: str) -> Path:
    """``accounts/<uuid>/agents/<agent>/workspace``（与 ``pnms``、``repo`` 同级）。"""
    p = agent_workspace_dir(user_uuid, agent_name) / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_config_path(user_uuid: str, agent_name: str) -> Path:
    return agent_workspace_dir(user_uuid, agent_name) / "agent.json"


def list_local_agent_workspaces(user_uuid: str) -> list[tuple[str, Path]]:
    """
    列出本机已初始化迹象的 Agent：返回 ``(展示名, 工作区目录)``。
    目录下存在 ``agent.json``、``pnms`` 或 ``repo`` 之一即视为已使用。
    """
    agents_root = account_dir(user_uuid) / "agents"
    if not agents_root.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for child in sorted(agents_root.iterdir()):
        if not child.is_dir():
            continue
        seg = child.name
        if (
            (child / "agent.json").is_file()
            or (child / "pnms").is_dir()
            or (child / "repo").is_dir()
        ):
            meta = load_agent_config(user_uuid, seg)
            display = str(meta.get("agent_name", seg)) if meta else seg
            out.append((display, agent_workspace_dir(user_uuid, seg)))
    out.sort(key=lambda t: t[0].lower())
    return out


def list_local_agent_names(user_uuid: str) -> list[str]:
    """``list_local_agent_workspaces`` 的展示名列表（去重保序）。"""
    seen: set[str] = set()
    names: list[str] = []
    for d, _ in list_local_agent_workspaces(user_uuid):
        if d not in seen:
            seen.add(d)
            names.append(d)
    return names


def load_agent_config(user_uuid: str, agent_name: str) -> dict[str, Any] | None:
    p = agent_config_path(user_uuid, agent_name)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_agent_config(
    user_uuid: str,
    agent_name: str,
    *,
    ssh_host: str,
    ssh_port: int | None,
    git_ssh_url: str,
) -> Path:
    """写入 ``agent.json``，并确保 ``pnms``、``workspace`` 目录存在。"""
    ws = agent_workspace_dir(user_uuid, agent_name)
    ws.mkdir(parents=True, exist_ok=True)
    agent_pnms_dir(user_uuid, agent_name).mkdir(parents=True, exist_ok=True)
    resolve_workspace_dir_for_user_agent(user_uuid, agent_name)
    data = {
        "agent_name": agent_name,
        "user_uuid": user_uuid,
        "ssh_host": ssh_host,
        "ssh_port": ssh_port,
        "git_ssh_url": git_ssh_url,
    }
    p = agent_config_path(user_uuid, agent_name)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def git_ssh_env(private_key_path: Path, *, ssh_port: int | None = None) -> dict[str, str]:
    """构造 ``GIT_SSH_COMMAND``，使用指定私钥（Ed25519）。"""
    key = str(private_key_path.expanduser().resolve())
    ssh_bin = get_env("MMEM_GIT_SSH") or "ssh"
    parts = [ssh_bin, "-i", key, "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=accept-new"]
    if ssh_port is not None and ssh_port > 0:
        parts.extend(["-p", str(int(ssh_port))])
    cmd = shlex.join(parts)
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = cmd
    return env


def git_clone_memory_repo(
    *,
    remote_url: str,
    dest: Path,
    private_key_path: Path,
    ssh_port: int | None = None,
) -> None:
    """若 ``dest`` 下尚无 ``.git``，则 ``git clone``。"""
    dest = dest.resolve()
    git_meta = dest / ".git"
    if git_meta.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = git_ssh_env(private_key_path, ssh_port=ssh_port)
    r = subprocess.run(
        ["git", "clone", remote_url, str(dest)],
        env=env,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git clone 失败: {r.stderr or r.stdout or r.returncode}")


def resolve_pnms_dir_for_user_agent(_cfg: MindMemoryClientConfig, user_uuid: str, agent_name: str) -> Path:
    """
    PNMS checkpoint 固定位于 ``accounts/<uuid>/agents/<agent>/pnms``（与其它 Agent 一致）。
    首参数保留用于签名兼容；不再写入 ``~/.mindmemory/pnms/<user>/<agent>/``。
    """
    pnms = agent_pnms_dir(user_uuid, agent_name)
    pnms.mkdir(parents=True, exist_ok=True)
    return pnms


def resolve_git_dir_for_sync(cfg: MindMemoryClientConfig, agent_name: str) -> Path | None:
    """
    同步时默认记忆仓库目录：已初始化 Agent 工作区时返回 ``.../repo``，否则 ``None``（由调用方回退 cwd 或 ``--git-dir``）。
    """
    if not cfg.user_uuid:
        return None
    ws = agent_workspace_dir(cfg.user_uuid, agent_name)
    if not agent_config_path(cfg.user_uuid, agent_name).is_file():
        return None
    return agent_git_dir(cfg.user_uuid, agent_name)


def ensure_agent_registered_on_server(cfg: MindMemoryClientConfig, agent_name: str) -> dict[str, Any]:
    """
    调用 ``begin-submit`` 使服务端创建 Agent 与 Gogs 仓库（若尚不存在），
    再 ``mark_completed(submission_ok=false)`` 释放锁，避免长期占锁。

    需已配置 ``user_uuid`` 与 ``private_key_path``。
    """
    from mindmemory_client.api import MmemApiClient

    if not cfg.user_uuid or not cfg.private_key_path:
        raise ValueError("ensure_agent_registered_on_server 需要 user_uuid 与 private_key_path")
    with MmemApiClient(cfg) as api:
        begin = api.begin_submit(cfg.user_uuid, agent_name, holder_info="mmem-agent-workspace-init")
        lock = str(begin.get("lock_uuid") or "")
        if not lock:
            raise RuntimeError("begin-submit 未返回 lock_uuid")
        api.mark_completed(
            cfg.user_uuid,
            agent_name,
            lock,
            submission_ok=False,
            commit_ids=[],
            error_message="mmem agent init：仅注册 Agent/仓库，无 Git 提交",
        )
        return begin


def ensure_default_agent_workspace(cfg: MindMemoryClientConfig) -> dict[str, Any]:
    """
    登录或注册成功后为默认 Agent（``DEFAULT_AGENT_NAME``）创建工作区，与 ``mmem agent init`` 目录结构一致。
    需已配置 ``user_uuid`` 与 ``private_key_path``。
    """
    import logging

    logger = logging.getLogger(__name__)
    out: dict[str, Any] = {"ok": False}
    if not cfg.user_uuid or not cfg.private_key_path:
        out["reason"] = "no_credentials"
        return out
    uid = cfg.user_uuid
    name = DEFAULT_AGENT_NAME
    if agent_config_path(uid, name).is_file():
        agent_pnms_dir(uid, name).mkdir(parents=True, exist_ok=True)
        resolve_workspace_dir_for_user_agent(uid, name)
        out["ok"] = True
        out["skipped"] = "already_initialized"
        return out

    host = (get_env("MMEM_GIT_SSH_HOST") or "").strip()
    port_raw = (get_env("MMEM_GIT_SSH_PORT") or "").strip()
    port: int | None = None
    if port_raw:
        try:
            port = int(port_raw)
        except ValueError:
            port = None

    if not host:
        host = "localhost"
        out["warning"] = (
            "MMEM_GIT_SSH_HOST 未设置，已用 localhost 占位；请配置后执行 "
            f"mmem agent init {name} 或编辑 agent.json 以同步记忆仓库。"
        )

    url = memory_repo_ssh_url(uid, name, ssh_host=host)

    try:
        ensure_agent_registered_on_server(cfg, name)
    except Exception as e:
        out["register_error"] = str(e)
        logger.warning("默认 Agent 服务端注册失败: %s", e)

    try:
        write_agent_config(uid, name, ssh_host=host, ssh_port=port, git_ssh_url=url)
    except Exception as e:
        out["error"] = str(e)
        return out

    repo = agent_git_dir(uid, name)
    if host and host != "localhost" and not (repo / ".git").exists():
        try:
            git_clone_memory_repo(
                remote_url=url,
                dest=repo,
                private_key_path=Path(cfg.private_key_path),
                ssh_port=port,
            )
        except Exception as e:
            out["clone_error"] = str(e)
            logger.warning("默认 Agent git clone 失败: %s", e)

    out["ok"] = True
    return out
