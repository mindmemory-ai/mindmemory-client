"""sync_manifest / mmem-workspace.json：解析与路径安全。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mindmemory_client.sync_manifest import (
    SUPPORTED_SCHEMA_VERSION,
    ManifestBundle,
    PromptSection,
    SyncManifestError,
    WorkspaceConfig,
    collect_files_for_include,
    load_workspace_config,
    manifest_paths_for_pack,
    prompt_context_paths_for_workspace,
    validate_include_pattern,
)


def _v2_doc(sync_includes: list, prompt_include: list | None = None) -> dict:
    d: dict = {
        "schema_version": "2",
        "sync": {"bundles": [{"id": "extras", "include": sync_includes, "optional": False}]},
    }
    if prompt_include is not None:
        d["prompt"] = {"include": prompt_include, "optional": True}
    return d


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
    m = WorkspaceConfig(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        sync_bundles=[ManifestBundle(id="extras", include=["p/core.md"], optional=False)],
    )
    files, w = manifest_paths_for_pack(tmp_path, m)
    assert not w
    assert len(files) == 1
    assert files[0][1] == "p/core.md"


def test_load_workspace_config_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "mmem-workspace.json"
    data = _v2_doc(["x.txt"], prompt_include=["x.txt"])
    data["sync"]["bundles"][0]["optional"] = True
    p.write_text(json.dumps(data), encoding="utf-8")
    m = load_workspace_config(p)
    assert m.sync_bundles[0].id == "extras"
    assert m.prompt is not None
    assert m.prompt.include == ["x.txt"]


def test_unknown_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text('{"schema_version": "99", "sync": {"bundles": []}}', encoding="utf-8")
    with pytest.raises(SyncManifestError):
        load_workspace_config(p)


def test_rejects_v1_top_level_bundles(tmp_path: Path) -> None:
    p = tmp_path / "legacy.json"
    p.write_text(
        '{"schema_version":"1","bundles":[{"id":"extras","include":["a"],"optional":false}]}',
        encoding="utf-8",
    )
    with pytest.raises(SyncManifestError):
        load_workspace_config(p)


def test_prompt_context_paths_for_workspace(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B", encoding="utf-8")
    m = WorkspaceConfig(
        schema_version="2",
        sync_bundles=[ManifestBundle(id="extras", include=["a.txt"], optional=False)],
        prompt=PromptSection(include=["b.txt"], optional=False),
    )
    paths, w = prompt_context_paths_for_workspace(tmp_path, m)
    assert not w
    assert [x[1] for x in paths] == ["b.txt"]
