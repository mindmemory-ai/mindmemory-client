"""pnms_bundle 解密、解压与 PNMS merge + save。"""

import io
import tarfile
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("pnms")

from pnms import PNMS, PNMSConfig, SimpleQueryEncoder

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.memory_crypto import encrypt_memory_base64
from mindmemory_client.memory_bundle import import_encrypted_bundle_to_agent_checkpoint


def test_import_bundle_roundtrip(tmp_path: Path) -> None:
    """与 sync push 相同格式：tar.gz（单顶层 pnms/）+ AES-GCM Base64。"""
    key = b"x" * 32
    src_pnms = tmp_path / "src_pnms"
    cfg0 = PNMSConfig()
    cfg0.embed_dim = 64
    cfg0.concept_checkpoint_dir = str(src_pnms)
    enc = SimpleQueryEncoder(embed_dim=64, vocab_size=10000)
    p = PNMS(config=cfg0, user_id="u1", encoder=enc, device=__import__("torch").device("cpu"))
    p.handle_query("hi", llm=lambda q, ctx: "ok", content_to_remember="x")
    p.save_concept_modules()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(src_pnms, arcname=src_pnms.name)
    bundle = tmp_path / "pnms_bundle.enc"
    bundle.write_text(encrypt_memory_base64(buf.getvalue(), key) + "\n", encoding="utf-8")

    dest = tmp_path / "accounts" / "user-1" / "agents" / "A1" / "pnms"
    mcfg = MindMemoryClientConfig(
        user_uuid="user-1",
        pnms_data_root=tmp_path / "accounts",
        agent_name="A1",
    )
    meta = import_encrypted_bundle_to_agent_checkpoint(
        bundle_path=bundle,
        key=key,
        dest_pnms_dir=dest,
        cfg=mcfg,
        user_uuid="user-1",
        agent_name="A1",
    )
    assert dest.is_dir()
    assert (dest / "meta.json").is_file()
    assert isinstance(meta.get("num_slots"), int)
