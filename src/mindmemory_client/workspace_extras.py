"""workspace extras：按 ``mmem-workspace.json`` 打包为 tar.gz + K_seed 加密；解密并解压回 ``workspace/``。"""

from __future__ import annotations

import io
import logging
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from mindmemory_client.memory_crypto import decrypt_memory_base64, encrypt_memory_base64
from mindmemory_client.sync_manifest import (
    WORKSPACE_CONFIG_FILENAME,
    SyncManifestError,
    WorkspaceConfig,
    load_workspace_config,
    manifest_paths_for_pack,
    resolve_workspace_config_path,
)

logger = logging.getLogger(__name__)


def pack_workspace_extras_to_enc(config: WorkspaceConfig, workspace_root: Path, key: bytes) -> str:
    """
    将 ``sync.bundles`` 列出的文件打成 tar.gz，再经 ``encrypt_memory_base64``（与 ``pnms_bundle.enc`` 相同）。
    返回 Base64 单行文本。
    """
    files, warnings = manifest_paths_for_pack(workspace_root, config)
    for w in warnings:
        logger.info("%s", w)
    if not files:
        raise SyncManifestError("未解析出任何可打包文件（或仅含被跳过项）")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for abs_path, arcname in files:
            tar.add(abs_path, arcname=arcname, recursive=False)

    return encrypt_memory_base64(buf.getvalue(), key)


def pack_workspace_extras_from_manifest_file(
    manifest_path: Path, workspace_root: Path, key: bytes
) -> str:
    """从 ``mmem-workspace.json`` 路径加载并打包。"""
    m = load_workspace_config(manifest_path)
    return pack_workspace_extras_to_enc(m, workspace_root, key)


def dry_run_workspace_extras_paths(
    workspace_root: Path,
    *,
    manifest_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    """
    解析配置，返回将写入 tar 的成员路径（相对 ``workspace_root`` 的 POSIX 路径）与 warnings。
    不加密、不写文件、不需要 ``K_seed``。
    """
    wp = workspace_root.resolve()
    if manifest_path is not None:
        mp = manifest_path
    else:
        resolved = resolve_workspace_config_path(wp)
        if resolved is None:
            raise SyncManifestError(f"未找到 {wp / WORKSPACE_CONFIG_FILENAME}")
        mp = resolved
    if not mp.is_file():
        raise SyncManifestError(f"未找到配置: {mp}")
    m = load_workspace_config(mp)
    files, warnings = manifest_paths_for_pack(wp, m)
    arcnames = [arc for _abs, arc in files]
    return arcnames, warnings


def decrypt_extras_bundle_bytes_to_workspace(
    plain_tgz: bytes,
    workspace_root: Path,
    *,
    overwrite_workspace_config: bool = False,
) -> dict[str, Any]:
    """
    将解密后的 tar.gz 字节解压到 ``workspace_root``。
    默认**跳过**写入 ``mmem-workspace.json``，除非 ``overwrite_workspace_config=True``。
    """
    workspace_root = workspace_root.resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    skipped: list[str] = []

    with tarfile.open(fileobj=io.BytesIO(plain_tgz), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            name = m.name
            rel = PurePosixPath(name)
            parts = rel.parts
            if ".." in parts:
                raise SyncManifestError(f"tar 内非法路径: {name!r}")
            rel_s = str(rel)
            if rel_s == WORKSPACE_CONFIG_FILENAME or rel_s.endswith("/" + WORKSPACE_CONFIG_FILENAME):
                if not overwrite_workspace_config:
                    skipped.append(rel_s)
                    continue
            dest = (workspace_root / Path(*parts)).resolve()
            try:
                dest.relative_to(workspace_root)
            except ValueError as e:
                raise SyncManifestError(f"tar 内路径越界: {name!r}") from e
            dest.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(m)
            if f is None:
                continue
            try:
                dest.write_bytes(f.read())
            finally:
                f.close()
            written.append(rel_s)

    return {"written": written, "skipped_workspace_config": skipped}


def decrypt_extras_bundle_file_to_workspace(
    bundle_path: Path,
    workspace_root: Path,
    key: bytes,
    *,
    overwrite_workspace_config: bool = False,
) -> dict[str, Any]:
    """读取密文文件（Base64 单行）→ 解密 → 解压到 workspace。"""
    b64 = bundle_path.read_text(encoding="utf-8").strip()
    plain = decrypt_memory_base64(b64, key)
    return decrypt_extras_bundle_bytes_to_workspace(
        plain, workspace_root, overwrite_workspace_config=overwrite_workspace_config
    )


def extras_bundle_path_in_repo(git_repo_root: Path) -> Path:
    """与 ``sync_manifest.EXTRAS_BUNDLE_REPO_RELPATH`` 一致。"""
    from mindmemory_client.sync_manifest import EXTRAS_BUNDLE_REPO_RELPATH

    return git_repo_root / EXTRAS_BUNDLE_REPO_RELPATH
