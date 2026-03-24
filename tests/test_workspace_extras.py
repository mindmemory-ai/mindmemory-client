"""workspace_extras：打包与解密往返。"""

from __future__ import annotations

from pathlib import Path

import pytest

from mindmemory_client.sync_manifest import (
    SUPPORTED_SCHEMA_VERSION,
    ManifestBundle,
    WorkspaceConfig,
    load_workspace_config,
)
from mindmemory_client.workspace_extras import (
    decrypt_extras_bundle_bytes_to_workspace,
    dry_run_workspace_extras_paths,
    pack_workspace_extras_to_enc,
    read_extras_enc_text_block,
)


def test_pack_and_decrypt_roundtrip(tmp_path: Path) -> None:
    key = b"x" * 32
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "core.md").write_text("hello", encoding="utf-8")

    m = WorkspaceConfig(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        sync_bundles=[ManifestBundle(id="extras", include=["persona/core.md"], optional=False)],
    )
    b64 = pack_workspace_extras_to_enc(m, tmp_path, key)
    assert isinstance(b64, str) and len(b64) > 10

    from mindmemory_client.memory_crypto import decrypt_memory_base64

    plain = decrypt_memory_base64(b64, key)

    out = tmp_path / "out"
    out.mkdir()
    meta = decrypt_extras_bundle_bytes_to_workspace(plain, out)
    assert (out / "persona" / "core.md").read_text(encoding="utf-8") == "hello"
    assert "persona/core.md" in meta["written"]


def test_dry_run_workspace_extras_paths(tmp_path: Path) -> None:
    key = b"x" * 32
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "core.md").write_text("hello", encoding="utf-8")
    cfg = tmp_path / "mmem-workspace.json"
    cfg.write_text(
        '{"schema_version":"2","sync":{"bundles":[{"id":"extras","include":["persona/core.md"],"optional":false}]}}',
        encoding="utf-8",
    )
    arcs, w = dry_run_workspace_extras_paths(tmp_path)
    assert arcs == ["persona/core.md"]
    assert not w
    m = load_workspace_config(cfg)
    b64 = pack_workspace_extras_to_enc(m, tmp_path, key)
    assert len(b64) > 10


def test_read_extras_enc_text_block_matches_pack(tmp_path: Path) -> None:
    key = b"x" * 32
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "core.md").write_text("hello", encoding="utf-8")

    m = WorkspaceConfig(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        sync_bundles=[ManifestBundle(id="extras", include=["persona/core.md"], optional=False)],
    )
    b64 = pack_workspace_extras_to_enc(m, tmp_path, key)
    enc_path = tmp_path / "extras.enc"
    enc_path.write_text(b64 + "\n", encoding="utf-8")

    text, warns = read_extras_enc_text_block(enc_path, key)
    assert not warns
    assert text
    assert "[persona/core.md]" in text
    assert "hello" in text


def test_read_extras_enc_text_block_skips_binary(tmp_path: Path) -> None:
    key = b"x" * 32
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "bad.bin").write_bytes(b"\xff\xfe")

    m = WorkspaceConfig(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        sync_bundles=[ManifestBundle(id="extras", include=["a/bad.bin"], optional=False)],
    )
    b64 = pack_workspace_extras_to_enc(m, tmp_path, key)
    enc_path = tmp_path / "e.enc"
    enc_path.write_text(b64, encoding="utf-8")
    text, warns = read_extras_enc_text_block(enc_path, key)
    assert text is None
    assert warns
    assert any("UTF-8" in w or "utf-8" in w.lower() for w in warns)
