"""workspace extras：按清单打包为 tar.gz + K_seed 加密；解密并解压回 ``workspace/``。"""

from __future__ import annotations

import io
import logging
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from mindmemory_client.memory_crypto import decrypt_memory_base64, encrypt_memory_base64
from mindmemory_client.sync_manifest import (
    MANIFEST_FILENAME,
    SyncManifest,
    SyncManifestError,
    load_sync_manifest,
    manifest_paths_for_pack,
)

logger = logging.getLogger(__name__)


def pack_workspace_extras_to_enc(manifest: SyncManifest, workspace_root: Path, key: bytes) -> str:
    """
    将清单中列出的文件打成 tar.gz，再经 ``encrypt_memory_base64``（与 ``pnms_bundle.enc`` 相同）。
    返回 Base64 单行文本。
    """
    files, warnings = manifest_paths_for_pack(workspace_root, manifest)
    for w in warnings:
        logger.info("%s", w)
    if not files:
        raise SyncManifestError("清单未解析出任何可打包文件（或仅含被跳过项）")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for abs_path, arcname in files:
            tar.add(abs_path, arcname=arcname, recursive=False)

    return encrypt_memory_base64(buf.getvalue(), key)


def pack_workspace_extras_from_manifest_file(
    manifest_path: Path, workspace_root: Path, key: bytes
) -> str:
    """从清单文件路径加载并打包。"""
    m = load_sync_manifest(manifest_path)
    return pack_workspace_extras_to_enc(m, workspace_root, key)


def decrypt_extras_bundle_bytes_to_workspace(
    plain_tgz: bytes,
    workspace_root: Path,
    *,
    overwrite_manifest: bool = False,
) -> dict[str, Any]:
    """
    将解密后的 tar.gz 字节解压到 ``workspace_root``。
    默认**跳过**写入 ``.mmem-sync-manifest.json``，除非 ``overwrite_manifest=True``。
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
            if rel_s == MANIFEST_FILENAME or rel_s.endswith("/" + MANIFEST_FILENAME):
                if not overwrite_manifest:
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

    return {"written": written, "skipped_manifest": skipped}


def decrypt_extras_bundle_file_to_workspace(
    bundle_path: Path,
    workspace_root: Path,
    key: bytes,
    *,
    overwrite_manifest: bool = False,
) -> dict[str, Any]:
    """读取密文文件（Base64 单行）→ 解密 → 解压到 workspace。"""
    b64 = bundle_path.read_text(encoding="utf-8").strip()
    plain = decrypt_memory_base64(b64, key)
    return decrypt_extras_bundle_bytes_to_workspace(
        plain, workspace_root, overwrite_manifest=overwrite_manifest
    )


def extras_bundle_path_in_repo(git_repo_root: Path) -> Path:
    """与 ``sync_manifest.EXTRAS_BUNDLE_REPO_RELPATH`` 一致。"""
    from mindmemory_client.sync_manifest import EXTRAS_BUNDLE_REPO_RELPATH

    return git_repo_root / EXTRAS_BUNDLE_REPO_RELPATH
