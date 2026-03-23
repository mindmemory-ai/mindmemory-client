from pathlib import Path

import pytest

from mindmemory_client.client_state import (
    AccountMeta,
    load_state,
    resolve_mmem_config,
    save_account_meta,
    save_state,
    write_private_key_file,
)
from mindmemory_client.config import DEFAULT_AGENT_NAME


@pytest.fixture
def isolated_mmem_home(monkeypatch, tmp_path: Path):
    """隔离 HOME 与客户端目录，避免读写真实 ``~/.mindmemory``。"""
    fake_home = tmp_path / "h"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    cfg = tmp_path / "config"
    data = tmp_path / "data"
    monkeypatch.setenv("MMEM_CLIENT_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("MMEM_CLIENT_DATA_DIR", str(data))
    monkeypatch.delenv("MMEM_USER_UUID", raising=False)
    monkeypatch.delenv("MMEM_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("MMEM_PNMS_DATA_ROOT", raising=False)
    monkeypatch.delenv("MMEM_CREDENTIAL_SOURCE", raising=False)
    return tmp_path


def test_resolve_uses_account_when_state_set(isolated_mmem_home, monkeypatch):
    uid = "550e8400-e29b-41d4-a716-446655440000"
    meta = AccountMeta(email="t@example.com", user_uuid=uid)
    save_account_meta(meta)
    write_private_key_file(uid, "dummy-not-valid-key")
    st = load_state()
    st.current_account_uuid = uid
    save_state(st)

    r = resolve_mmem_config()
    assert r.user_uuid == uid
    assert r.private_key_path is not None
    assert uid in str(r.private_key_path)
    assert r.pnms_data_root == isolated_mmem_home / "data"
    assert r.agent_name == DEFAULT_AGENT_NAME


def test_resolve_uses_current_agent_from_state(isolated_mmem_home, monkeypatch):
    uid = "550e8400-e29b-41d4-a716-446655440000"
    meta = AccountMeta(email="t@example.com", user_uuid=uid)
    save_account_meta(meta)
    write_private_key_file(uid, "dummy-not-valid-key")
    st = load_state()
    st.current_account_uuid = uid
    st.current_agent_name = "my-bot"
    save_state(st)

    r = resolve_mmem_config()
    assert r.agent_name == "my-bot"

    r2 = resolve_mmem_config(agent_name_override="explicit")
    assert r2.agent_name == "explicit"


def test_resolve_env_overrides_account(isolated_mmem_home, monkeypatch):
    uid = "550e8400-e29b-41d4-a716-446655440000"
    meta = AccountMeta(email="t@example.com", user_uuid=uid)
    save_account_meta(meta)
    write_private_key_file(uid, "x")
    st = load_state()
    st.current_account_uuid = uid
    save_state(st)

    pk = isolated_mmem_home / "override_key"
    pk.write_text("x")
    monkeypatch.setenv("MMEM_CREDENTIAL_SOURCE", "env")
    monkeypatch.setenv("MMEM_USER_UUID", "other-uuid")
    monkeypatch.setenv("MMEM_PRIVATE_KEY_PATH", str(pk))

    r = resolve_mmem_config()
    assert r.user_uuid == "other-uuid"
    assert r.private_key_path == pk
