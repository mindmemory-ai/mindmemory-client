"""sync_manifest：清单解析与路径安全。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mindmemory_client.sync_manifest import (
    SUPPORTED_SCHEMA_VERSION,
    SyncManifest,
    SyncManifestError,
    collect_files_for_include,
    load_sync_manifest,
    manifest_paths_for_pack,
    validate_include_pattern,
)


def test_validate_include_rejects_traversal() -> None:
    with pytest.raises(SyncManifestError):
        validate_include_pattern("../x")
    with pytest.raises(SyncManifestError):
        validate_include_pattern("/abs")


def test_collect_files_for_include(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("x", encoding="utf-8")
    got = collect_files_for_include(tmp_path, "a/f.txt")
    assert len(got) == 1
    assert got[0].name == "f.txt"


def test_manifest_paths_for_pack(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "core.md").write_text("m", encoding="utf-8")
    m = SyncManifest(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        bundles=[{"id": "extras", "include": ["p/core.md"], "optional": False}],
    )
    files, w = manifest_paths_for_pack(tmp_path, m)
    assert not w
    assert len(files) == 1
    assert files[0][1] == "p/core.md"


def test_load_sync_manifest_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / ".mmem-sync-manifest.json"
    data = {
        "schema_version": "1",
        "bundles": [{"id": "extras", "include": ["x.txt"], "optional": True}],
    }
    p.write_text(json.dumps(data), encoding="utf-8")
    m = load_sync_manifest(p)
    assert m.bundles[0].id == "extras"


def test_unknown_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text('{"schema_version": "99", "bundles": []}', encoding="utf-8")
    with pytest.raises(SyncManifestError):
        load_sync_manifest(p)
