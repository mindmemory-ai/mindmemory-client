"""workspace 提示拼装与 BT-7274 内置模板。"""

import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from mindmemory_client.sync_manifest import WORKSPACE_CONFIG_FILENAME
from mindmemory_client.workspace_prompt import merge_workspace_prompt_and_extras, read_workspace_prompt_block


def test_bt7274_template_shipped_in_package() -> None:
    root = files("mindmemory_client").joinpath("agent", "BT-7274", "workspace")
    assert root.is_dir(), "pip install 需包含 package-data: agent/**/*"
    names = {e.name for e in root.iterdir() if e.is_file()}
    assert WORKSPACE_CONFIG_FILENAME in names
    assert "identity.md" in names
    assert "soul.md" in names


def test_merge_workspace_prompt_and_extras() -> None:
    m = merge_workspace_prompt_and_extras(
        "[p]\nx",
        "[f]\ny",
        extras_section_intro="[extras]",
    )
    assert m
    assert "[p]" in m
    assert "[extras]" in m
    assert "[f]" in m
    assert "---" in m


def test_merge_workspace_prompt_and_extras_extras_only() -> None:
    m = merge_workspace_prompt_and_extras(None, "only", extras_section_intro="E")
    assert m == "E\n\nonly"


def test_read_workspace_prompt_block_from_template_copy(tmp_path: Path) -> None:
    root = files("mindmemory_client").joinpath("agent", "BT-7274", "workspace")
    for entry in root.iterdir():
        if entry.is_file():
            (tmp_path / entry.name).write_bytes(entry.read_bytes())
    text, warns = read_workspace_prompt_block(tmp_path)
    assert text
    assert not warns or isinstance(warns, list)
    assert "身份" in text or "identity" in text.lower()


def test_seed_default_workspace_template(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from mindmemory_client import agent_workspace as aw

    monkeypatch.setattr(aw, "account_dir", lambda u: tmp_path / "accounts" / u)
    uid = "00000000-0000-0000-0000-000000000001"
    ok = aw.seed_default_workspace_template(uid, "BT-7274")
    assert ok
    ws = tmp_path / "accounts" / uid / "agents" / "BT-7274" / "workspace"
    assert (ws / WORKSPACE_CONFIG_FILENAME).is_file()
    assert (ws / "identity.md").is_file()
    assert (ws / "soul.md").is_file()
    ok2 = aw.seed_default_workspace_template(uid, "BT-7274")
    assert not ok2


def test_agent_workspace_mirror_script_ok() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "tools" / "check_agent_workspace_mirror.py"
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
