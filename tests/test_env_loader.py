from pathlib import Path

import pytest

from mindmemory_client.env_loader import (
    ensure_dotenv_loaded,
    get_env,
    reset_dotenv_loaded,
)


def test_dotenv_loads_cwd_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_ENV_FILE", raising=False)
    monkeypatch.delenv("MMEM_BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MMEM_BASE_URL=http://from-dotenv:9999\n", encoding="utf-8")
    reset_dotenv_loaded()
    ensure_dotenv_loaded()
    assert get_env("MMEM_BASE_URL") == "http://from-dotenv:9999"


def test_shell_env_wins_over_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_ENV_FILE", raising=False)
    monkeypatch.setenv("MMEM_BASE_URL", "http://from-shell:1")
    # 避免本机 ~/.mindmemory/.env 与 cwd/.env 双文件时后者 override=True 覆盖 shell
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MMEM_BASE_URL=http://from-dotenv:2\n", encoding="utf-8")
    reset_dotenv_loaded()
    ensure_dotenv_loaded()
    assert get_env("MMEM_BASE_URL") == "http://from-shell:1"


def test_mmem_env_file_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_BASE_URL", raising=False)
    a = tmp_path / "a.env"
    b = tmp_path / "b.env"
    a.write_text("MMEM_BASE_URL=http://a\n", encoding="utf-8")
    b.write_text("MMEM_BASE_URL=http://b\n", encoding="utf-8")
    monkeypatch.setenv("MMEM_ENV_FILE", str(b))
    monkeypatch.chdir(tmp_path)
    reset_dotenv_loaded()
    ensure_dotenv_loaded()
    assert get_env("MMEM_BASE_URL") == "http://b"


def test_dotenv_loads_user_mindmemory_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``~/.mindmemory/.env``（由 HOME 决定）与 cwd/.env 的加载顺序。"""
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_ENV_FILE", raising=False)
    monkeypatch.delenv("MMEM_BASE_URL", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    mm = fake_home / ".mindmemory"
    mm.mkdir()
    (mm / ".env").write_text("MMEM_BASE_URL=http://from-user\n", encoding="utf-8")
    work = tmp_path / "proj"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / ".env").write_text("MMEM_BASE_URL=http://from-cwd\n", encoding="utf-8")
    reset_dotenv_loaded()
    ensure_dotenv_loaded()
    assert get_env("MMEM_BASE_URL") == "http://from-cwd"


def test_dotenv_loads_only_user_mindmemory_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """仅存在 ``~/.mindmemory/.env``、项目目录无 ``.env`` 时也能加载。"""
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_ENV_FILE", raising=False)
    monkeypatch.delenv("MMEM_BASE_URL", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    mm = fake_home / ".mindmemory"
    mm.mkdir()
    (mm / ".env").write_text("MMEM_BASE_URL=http://user-only\n", encoding="utf-8")
    work = tmp_path / "proj"
    work.mkdir()
    monkeypatch.chdir(work)
    reset_dotenv_loaded()
    ensure_dotenv_loaded()
    assert get_env("MMEM_BASE_URL") == "http://user-only"
