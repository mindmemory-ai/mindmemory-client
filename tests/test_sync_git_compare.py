"""git compare 辅助逻辑（导入 mmem_cli.main 私有函数做回归）。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from mmem_cli.main import _git_compare_with_remote, _git_fetch_origin


def test_compare_no_remote_branch(tmp_path: Path) -> None:
    """无 origin 远程引用时 rev-parse origin/v1 失败 → no_remote_branch。"""
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@t.local"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "test"],
        check=True,
    )
    (repo / "f").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)

    assert _git_compare_with_remote(repo, "v1") == "no_remote_branch"


def test_compare_up_to_date_after_fetch(tmp_path: Path) -> None:
    """bare origin + clone：fetch 后与 origin/v1 一致 → up_to_date。"""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    w1 = tmp_path / "w1"
    subprocess.run(["git", "clone", str(bare), str(w1)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(w1), "config", "user.email", "t@t.local"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(w1), "config", "user.name", "test"],
        check=True,
    )
    (w1 / "a").write_text("1", encoding="utf-8")
    subprocess.run(["git", "-C", str(w1), "add", "a"], check=True)
    subprocess.run(["git", "-C", str(w1), "commit", "-m", "c1"], check=True)
    subprocess.run(
        ["git", "-C", str(w1), "push", "-u", "origin", "HEAD:refs/heads/v1"],
        check=True,
        capture_output=True,
    )

    w2 = tmp_path / "w2"
    subprocess.run(["git", "clone", str(bare), str(w2)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(w2), "checkout", "-b", "v1", "origin/v1"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(w2), "config", "user.email", "t@t.local"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(w2), "config", "user.name", "test"],
        check=True,
    )

    _git_fetch_origin(w2)
    assert _git_compare_with_remote(w2, "v1") == "up_to_date"
