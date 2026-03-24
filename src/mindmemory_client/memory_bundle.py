"""加密 bundle 解密、解压并与本地 checkpoint 融合；唯一入口在 mindmemory_client 内，CLI 只调此处。"""

from __future__ import annotations

import io
import logging
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.memory_crypto import decrypt_memory_base64
from mindmemory_client.memory_errors import MemoryEngineError, wrap_engine_exception
from mindmemory_client.pnms_bridge import PnmsMemoryBridge, peek_checkpoint_version_info

logger = logging.getLogger(__name__)


def format_memory_engine_error(exc: BaseException) -> str:
    """将 ``MemoryEngineError`` / 合并相关错误转为可读说明。"""
    if isinstance(exc, MemoryEngineError) and exc.code:
        code = exc.code
        base = str(exc)
        if code == "E_MERGE_CHECKPOINT_NOT_FOUND":
            return f"源 checkpoint 不可用（路径不存在或无法读取）: {base}"
        if code == "E_MERGE_VERSION_INCOMPATIBLE":
            return f"源记忆格式版本高于当前引擎，无法合并（仅支持向下兼容）: {base}"
        if code == "E_MERGE_INVALID_ARGUMENT":
            return f"合并被拒绝（参数非法、版本探测失败或槽数据与维度不一致等）: {base}"
        if code == "E_MERGE_NOT_IMPLEMENTED":
            return f"合并未实现: {base}"
        return f"[{code}] {base}"
    return str(exc)


def decrypt_pnms_bundle_file(bundle_path: Path, key: bytes) -> bytes:
    """读取 Base64 单行密文并解密为 tar.gz 原始字节。"""
    b64 = bundle_path.read_text(encoding="utf-8").strip()
    return decrypt_memory_base64(b64, key)


def _extract_tar_gz_source_root(plain: bytes) -> tuple[Path, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="mmem-pnms-import-"))
    try:
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
            if sys.version_info >= (3, 12):
                tar.extractall(tmp, filter="data")
            else:
                tar.extractall(tmp)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    children = list(tmp.iterdir())
    if not children:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError("bundle 解压后为空（非法 tar）")
    if len(children) == 1 and children[0].is_dir():
        return tmp, children[0]
    return tmp, tmp


def import_encrypted_bundle_to_agent_checkpoint(
    *,
    bundle_path: Path,
    key: bytes,
    dest_pnms_dir: Path,
    cfg: MindMemoryClientConfig,
    user_uuid: str,
    agent_name: str,
    expected_memory_format_version: str | None = None,
) -> dict[str, Any]:
    """
    解密 bundle → 解压到临时目录 → 在已加载本地 ``dest_pnms_dir`` 的引擎上合并外部 checkpoint，
    再持久化到该目录。不整目录覆盖；融合语义由底层引擎 ``merge_memories`` 决定。
    """
    plain = decrypt_pnms_bundle_file(bundle_path, key)
    work, src = _extract_tar_gz_source_root(plain)
    num_slots = 0
    try:
        dest_pnms_dir.mkdir(parents=True, exist_ok=True)
        bridge = PnmsMemoryBridge(
            cfg.pnms_data_root,
            user_uuid,
            agent_name,
            checkpoint_dir=dest_pnms_dir,
        )
        try:
            bridge.merge_external_checkpoint(str(src), expected_memory_format_version)
        except Exception as e:
            w = wrap_engine_exception(e)
            if isinstance(w, MemoryEngineError):
                raise w from e
            raise
        bridge.persist_checkpoint()
        num_slots = bridge.get_slot_count()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    meta: dict[str, Any] = {
        "dest_pnms_dir": str(dest_pnms_dir.resolve()),
        "num_slots": num_slots,
    }
    peek = peek_checkpoint_version_info(dest_pnms_dir)
    if peek is not None:
        meta["checkpoint_peek"] = peek
    logger.info("memory bundle import (merge): %s", meta)
    return meta
