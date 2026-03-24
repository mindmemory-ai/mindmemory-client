"""Workspace 配置 ``mmem-workspace.json``：同步（extras）与可选 LLM 提示路径（见 docs/memory-repo-extended-layout.md）。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

WORKSPACE_CONFIG_FILENAME = "mmem-workspace.json"
SUPPORTED_SCHEMA_VERSION = "2"

# 兼容旧导出（曾名 MANIFEST_FILENAME）
MANIFEST_FILENAME = WORKSPACE_CONFIG_FILENAME

# 记忆 Git 仓内 extras 密文相对路径（固定）
EXTRAS_BUNDLE_REPO_RELPATH = Path("mmem/bundles/extras.enc")


class ManifestBundle(BaseModel):
    """``sync.bundles`` 单项：打进 ``mmem/bundles/extras.enc``。"""

    id: str = Field(min_length=1)
    include: list[str] = Field(default_factory=list)
    optional: bool = False


class PromptSection(BaseModel):
    """可选：宿主拼接 LLM 上下文时读取的路径（相对 ``workspace/``），可与 sync 子集不同。"""

    include: list[str] = Field(default_factory=list)
    optional: bool = True


class WorkspaceConfig(BaseModel):
    """根配置：仅支持 ``schema_version`` == ``\"2\"``。"""

    schema_version: str
    updated_at: str | None = None
    note: str | None = None
    sync_bundles: list[ManifestBundle] = Field(default_factory=list)
    prompt: PromptSection | None = None

    @property
    def bundles(self) -> list[ManifestBundle]:
        return self.sync_bundles


class SyncManifestError(ValueError):
    """配置或路径非法。"""


def load_workspace_config(path: Path) -> WorkspaceConfig:
    """从 ``mmem-workspace.json`` 加载（仅 ``schema_version: 2``）。"""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SyncManifestError(f"配置 JSON 无效: {path}: {e}") from e
    if not isinstance(data, dict):
        raise SyncManifestError("根必须是 JSON object")

    sv = str(data.get("schema_version", ""))
    if sv != SUPPORTED_SCHEMA_VERSION:
        raise SyncManifestError(
            f"需要 schema_version={SUPPORTED_SCHEMA_VERSION!r}，当前为 {sv!r}"
        )

    updated_at = data.get("updated_at")
    if updated_at is not None and not isinstance(updated_at, str):
        updated_at = None
    note = data.get("note")
    if note is not None and not isinstance(note, str):
        note = None

    sync = data.get("sync")
    if not isinstance(sync, dict):
        raise SyncManifestError("需要 sync 对象")
    raw_bundles = sync.get("bundles")
    if not isinstance(raw_bundles, list):
        raise SyncManifestError("需要 sync.bundles 数组")
    sync_bundles = [ManifestBundle.model_validate(b) for b in raw_bundles]

    prompt: PromptSection | None = None
    raw_prompt = data.get("prompt")
    if raw_prompt is not None:
        if not isinstance(raw_prompt, dict):
            raise SyncManifestError("prompt 必须是 object 或省略")
        prompt = PromptSection.model_validate(raw_prompt)

    return WorkspaceConfig(
        schema_version=sv,
        updated_at=updated_at,
        note=note,
        sync_bundles=sync_bundles,
        prompt=prompt,
    )


def resolve_workspace_config_path(workspace_root: Path) -> Path | None:
    """若存在则返回 ``<workspace>/mmem-workspace.json``。"""
    p = workspace_root.resolve() / WORKSPACE_CONFIG_FILENAME
    return p if p.is_file() else None


def _normalize_rel_str(raw: str) -> str:
    s = raw.strip().replace("\\", "/")
    if not s:
        raise SyncManifestError("include 项不能为空")
    if s.startswith("/"):
        raise SyncManifestError(f"禁止绝对路径: {raw!r}")
    pp = PurePosixPath(s)
    if ".." in pp.parts:
        raise SyncManifestError(f"禁止路径穿越 '..': {raw!r}")
    return str(pp)


def validate_include_pattern(pattern: str) -> str:
    return _normalize_rel_str(pattern)


def collect_files_for_include(workspace: Path, include: str) -> list[Path]:
    pat = validate_include_pattern(include)
    wp = workspace.resolve()
    if not wp.is_dir():
        raise SyncManifestError(f"workspace 不是目录: {wp}")

    meta_chars = re.compile(r"[\*\?\[]")
    if meta_chars.search(pat):
        paths = sorted(p for p in wp.glob(pat) if p.is_file())
        return paths

    rel = Path(pat)
    target = (wp / rel).resolve()
    try:
        target.relative_to(wp)
    except ValueError as e:
        raise SyncManifestError(f"路径越界: {include!r}") from e
    if not target.exists():
        return []
    if target.is_file():
        return [target]
    if target.is_dir():
        raise SyncManifestError(f"include 指向目录而非文件: {include!r}（请使用 glob 或逐文件列出）")
    return []


def _is_reserved_workspace_file(rel_s: str) -> bool:
    if rel_s == WORKSPACE_CONFIG_FILENAME or rel_s.endswith("/" + WORKSPACE_CONFIG_FILENAME):
        return True
    return False


def manifest_paths_for_pack(workspace: Path, config: WorkspaceConfig) -> tuple[list[tuple[Path, str]], list[str]]:
    seen: dict[str, Path] = {}
    warnings: list[str] = []

    for bundle in config.sync_bundles:
        bid = bundle.id
        for inc in bundle.include:
            try:
                paths = collect_files_for_include(workspace, inc)
            except SyncManifestError as e:
                if bundle.optional:
                    warnings.append(f"[bundle {bid}] 跳过 include {inc!r}: {e}")
                    continue
                raise

            if not paths:
                msg = f"[bundle {bid}] 未匹配任何文件: {inc!r}"
                if bundle.optional:
                    warnings.append(msg)
                    continue
                raise SyncManifestError(msg)

            for p in paths:
                rel = p.resolve().relative_to(workspace.resolve())
                rel_s = rel.as_posix()
                if _is_reserved_workspace_file(rel_s):
                    warnings.append(f"跳过 workspace 配置文件: {rel_s}")
                    continue
                seen[rel_s] = p

    ordered = sorted(seen.items(), key=lambda x: x[0])
    files = [(path, posix) for posix, path in ordered]
    return files, warnings


def prompt_context_paths_for_workspace(
    workspace: Path, config: WorkspaceConfig
) -> tuple[list[tuple[Path, str]], list[str]]:
    if config.prompt is None or not config.prompt.include:
        return [], []

    seen: dict[str, Path] = {}
    warnings: list[str] = []
    opt = config.prompt.optional

    for inc in config.prompt.include:
        try:
            paths = collect_files_for_include(workspace, inc)
        except SyncManifestError as e:
            if opt:
                warnings.append(f"[prompt] 跳过 include {inc!r}: {e}")
                continue
            raise

        if not paths:
            msg = f"[prompt] 未匹配任何文件: {inc!r}"
            if opt:
                warnings.append(msg)
                continue
            raise SyncManifestError(msg)

        for p in paths:
            rel = p.resolve().relative_to(workspace.resolve())
            rel_s = rel.as_posix()
            if _is_reserved_workspace_file(rel_s):
                warnings.append(f"[prompt] 跳过配置文件: {rel_s}")
                continue
            seen[rel_s] = p

    ordered = sorted(seen.items(), key=lambda x: x[0])
    files = [(path, posix) for posix, path in ordered]
    return files, warnings
