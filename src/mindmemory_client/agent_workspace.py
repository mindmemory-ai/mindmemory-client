"""
Agent 工作区：账号目录下 ``accounts/<user_uuid>/agents/<agent>/``，
含 PNMS 数据（``pnms/``）与记忆 Git 仓库（``repo/``）。

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
from mindmemory_client.config import MindMemoryClientConfig
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


def agent_config_path(user_uuid: str, agent_name: str) -> Path:
    return agent_workspace_dir(user_uuid, agent_name) / "agent.json"


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
    """写入 ``agent.json``，并确保 ``pnms`` 目录存在。"""
    ws = agent_workspace_dir(user_uuid, agent_name)
    ws.mkdir(parents=True, exist_ok=True)
    agent_pnms_dir(user_uuid, agent_name).mkdir(parents=True, exist_ok=True)
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


def resolve_pnms_dir_for_user_agent(cfg: MindMemoryClientConfig, user_uuid: str, agent_name: str) -> Path:
    """
    若已为该 Agent 初始化工作区（存在 ``agent.json`` 或 ``.../pnms`` 目录），
    则 PNMS 使用 ``accounts/.../agents/.../pnms``；否则沿用 ``MMEM_PNMS_DATA_ROOT/<user>/<agent>/``。
    """
    ws = agent_workspace_dir(user_uuid, agent_name)
    pnms = agent_pnms_dir(user_uuid, agent_name)
    if agent_config_path(user_uuid, agent_name).is_file() or pnms.is_dir():
        return pnms
    from mindmemory_client.pnms_bridge import resolve_pnms_data_dir

    return resolve_pnms_data_dir(Path(cfg.pnms_data_root), user_uuid, agent_name)


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
