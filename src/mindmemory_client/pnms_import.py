"""从 ``pnms_bundle.enc`` 解密、解压到临时目录，再调用 PNMS ``merge`` 与远端 checkpoint 做数据融合，最后 ``save_concept_modules`` 落盘。"""

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

logger = logging.getLogger(__name__)


def format_pnms_merge_error(exc: BaseException) -> str:
    """将 PNMS 合并相关异常的 ``code`` 转为可读说明（与 docs/pnms_api.md §6 一致）。"""
    try:
        from pnms import ErrorCodes, PNMSError
    except ImportError:
        return str(exc)
    if isinstance(exc, PNMSError) and getattr(exc, "code", None):
        code = exc.code
        base = str(exc)
        if code == ErrorCodes.MERGE_CHECKPOINT_NOT_FOUND:
            return f"源 checkpoint 不可用（路径不存在或无法读取）: {base}"
        if code == ErrorCodes.MERGE_VERSION_INCOMPATIBLE:
            return f"源记忆格式版本高于当前 PNMS，无法合并（仅支持向下兼容）: {base}"
        if code == ErrorCodes.MERGE_INVALID_ARGUMENT:
            return f"合并被拒绝（参数非法、版本探测失败或槽数据与 embed_dim 不一致等）: {base}"
        if code == ErrorCodes.MERGE_NOT_IMPLEMENTED:
            return f"PNMS 合并未实现: {base}"
        return f"[{code}] {base}"
    return str(exc)


def decrypt_pnms_bundle_file(bundle_path: Path, key: bytes) -> bytes:
    """读取 Base64 单行密文并解密为 tar.gz 原始字节。"""
    b64 = bundle_path.read_text(encoding="utf-8").strip()
    return decrypt_memory_base64(b64, key)


def _extract_tar_gz_source_root(plain: bytes) -> tuple[Path, Path]:
    """
    将 tar.gz 解压到临时目录，返回 ``(temp_workdir, source_dir)``。
    ``source_dir`` 为与 ``sync push`` 打包时一致的顶层目录（内含 ``meta.json`` 等）。
    """
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


def import_pnms_bundle_to_agent_checkpoint(
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
    解密 bundle → 解压到临时目录 → 在**已加载本地** ``dest_pnms_dir`` 的引擎上调用
    ``PNMSClient.merge``，将源 checkpoint 与当前运行态记忆融合 → ``save_concept_modules`` 写回 ``dest_pnms_dir``。

    不会在合并前整目录覆盖 ``dest_pnms_dir``；融合语义由 PNMS ``merge_memories`` 实现。
    """
    from mindmemory_client.pnms_bridge import PnmsMemoryBridge

    try:
        from pnms import peek_checkpoint_versions
    except ImportError:
        peek_checkpoint_versions = None  # type: ignore[assignment]

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
        bridge.pnms.merge(
            bridge.user_id,
            str(src),
            source_memory_format_version=expected_memory_format_version,
        )
        engine = bridge.pnms.get_engine(bridge.user_id)
        engine.save_concept_modules(path=str(dest_pnms_dir))
        num_slots = engine.store.num_slots
    finally:
        shutil.rmtree(work, ignore_errors=True)

    meta: dict[str, Any] = {
        "dest_pnms_dir": str(dest_pnms_dir.resolve()),
        "num_slots": num_slots,
    }
    if peek_checkpoint_versions is not None:
        meta["checkpoint_peek"] = peek_checkpoint_versions(dest_pnms_dir)
    logger.info("PNMS import-bundle (merge): %s", meta)
    return meta
