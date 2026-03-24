"""运行时清单 ``.mmem-sync-manifest.json``：解析与路径校验（见 docs/memory-repo-extended-layout.md）。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSION = "1"
MANIFEST_FILENAME = ".mmem-sync-manifest.json"

# 记忆 Git 仓内 extras 密文相对路径（首轮固定）
EXTRAS_BUNDLE_REPO_RELPATH = Path("mmem/bundles/extras.enc")


class ManifestBundle(BaseModel):
    """单个 bundle：``include`` 为相对 ``workspace/`` 的路径或 glob。"""

    id: str = Field(min_length=1)
    include: list[str] = Field(default_factory=list)
    optional: bool = False


class SyncManifest(BaseModel):
    schema_version: str
    updated_at: str | None = None
    bundles: list[ManifestBundle] = Field(default_factory=list)
    note: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _schema_supported(cls, v: str) -> str:
        if v != SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                f"不支持的 schema_version={v!r}，当前仅支持 {SUPPORTED_SCHEMA_VERSION!r}"
            )
        return v


class SyncManifestError(ValueError):
    """清单或路径非法。"""


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
    """校验单条 include（glob 或字面路径），返回规范化 POSIX 风格字符串。"""
    return _normalize_rel_str(pattern)


def collect_files_for_include(workspace: Path, include: str) -> list[Path]:
    """
    将一条 include 解析为 ``workspace`` 下的现有文件路径列表。
    含 glob 元字符时使用 ``Path.glob``（相对于 ``workspace``）。
    """
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


def load_sync_manifest(path: Path) -> SyncManifest:
    """从 JSON 文件加载并校验。"""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SyncManifestError(f"清单 JSON 无效: {path}: {e}") from e
    if not isinstance(data, dict):
        raise SyncManifestError("清单根必须是 JSON object")
    try:
        return SyncManifest.model_validate(data)
    except Exception as e:
        raise SyncManifestError(f"清单校验失败: {e}") from e


def manifest_paths_for_pack(workspace: Path, manifest: SyncManifest) -> tuple[list[tuple[Path, str]], list[str]]:
    """
    返回 ``(files, warnings)``：``files`` 为 ``(绝对路径, tar 内相对路径 posix)``；
    tar 内路径为相对 ``workspace`` 的路径（不含 bundle id 前缀，与文档「解压回 workspace」一致）。
    若两条 include 命中同一文件，后者覆盖（去重保留最后一次）。
    """
    seen: dict[str, Path] = {}
    warnings: list[str] = []

    for bundle in manifest.bundles:
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
                if rel_s == MANIFEST_FILENAME or rel_s.endswith("/" + MANIFEST_FILENAME):
                    warnings.append(f"跳过清单文件自身: {rel_s}")
                    continue
                seen[rel_s] = p

    ordered = sorted(seen.items(), key=lambda x: x[0])
    files = [(path, posix) for posix, path in ordered]
    return files, warnings
