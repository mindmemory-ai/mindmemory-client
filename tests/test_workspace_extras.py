"""workspace_extras：打包与解密往返。"""

from __future__ import annotations

from pathlib import Path

import pytest

from mindmemory_client.sync_manifest import SUPPORTED_SCHEMA_VERSION, SyncManifest, load_sync_manifest
from mindmemory_client.workspace_extras import (
    decrypt_extras_bundle_bytes_to_workspace,
    dry_run_workspace_extras_paths,
    pack_workspace_extras_to_enc,
)


def test_pack_and_decrypt_roundtrip(tmp_path: Path) -> None:
    key = b"x" * 32
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "core.md").write_text("hello", encoding="utf-8")

    m = SyncManifest(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        bundles=[{"id": "extras", "include": ["persona/core.md"], "optional": False}],
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


def test_dry_run_workspace_extras_paths(tmp_path):
    key = b"x" * 32
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "core.md").write_text("hello", encoding="utf-8")
    man = tmp_path / ".mmem-sync-manifest.json"
    man.write_text(
        '{"schema_version":"1","bundles":[{"id":"extras","include":["persona/core.md"],"optional":false}]}',
        encoding="utf-8",
    )
    arcs, w = dry_run_workspace_extras_paths(tmp_path)
    assert arcs == ["persona/core.md"]
    assert not w
    m = load_sync_manifest(man)
    b64 = pack_workspace_extras_to_enc(m, tmp_path, key)
    assert len(b64) > 10
