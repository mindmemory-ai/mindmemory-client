"""从 ``workspace/mmem-workspace.json`` 的 ``prompt`` 段读取文件，供 CLI/宿主拼装系统提示。"""

from __future__ import annotations

import logging
from pathlib import Path

from mindmemory_client.sync_manifest import (
    SyncManifestError,
    load_workspace_config,
    prompt_context_paths_for_workspace,
    resolve_workspace_config_path,
)

logger = logging.getLogger(__name__)


def read_workspace_prompt_block(workspace_root: Path) -> tuple[str | None, list[str]]:
    """
    若存在 ``mmem-workspace.json`` 且配置了 ``prompt.include``，
    则读取匹配文件并拼接为一块文本（带 ``[相对路径]`` 标题）。

    返回 ``(text, warnings)``；无配置或无可读内容时 ``text`` 为 ``None``。
    """
    wp = workspace_root.resolve()
    mp = resolve_workspace_config_path(wp)
    if mp is None or not mp.is_file():
        return None, []

    try:
        cfg = load_workspace_config(mp)
    except SyncManifestError as e:
        return None, [str(e)]

    files, warnings = prompt_context_paths_for_workspace(wp, cfg)
    if not files:
        return None, warnings

    parts: list[str] = []
    for path, posix in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            warnings.append(f"无法读取 {posix}: {e}")
            continue
        parts.append(f"[{posix}]\n{text.strip()}")

    if not parts:
        return None, warnings
    return "\n\n".join(parts), warnings


def merge_workspace_prompt_and_extras(
    prompt_block: str | None,
    extras_block: str | None,
    *,
    extras_section_intro: str,
) -> str | None:
    """
    按 memory-repo-extended-layout §6：先 ``prompt`` 明文，再 extras 解密片段（由调用方传入已解密的 ``extras_block``）。
    """
    chunks: list[str] = []
    if prompt_block and prompt_block.strip():
        chunks.append(prompt_block.strip())
    if extras_block and extras_block.strip():
        chunks.append(extras_section_intro.strip() + "\n\n" + extras_block.strip())
    if not chunks:
        return None
    return "\n\n---\n\n".join(chunks)
