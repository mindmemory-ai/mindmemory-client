"""chat_strings：语言解析与键完整性。"""

import pytest

from mindmemory_client.chat_strings import chat_strings, get_chat_lang


def test_chat_strings_zh_en_have_same_keys() -> None:
    zk = set(chat_strings("zh").keys())
    ek = set(chat_strings("en").keys())
    assert zk == ek


def test_get_chat_lang_respects_mmem_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MMEM_LANG", "en")
    assert get_chat_lang() == "en"
    monkeypatch.setenv("MMEM_LANG", "zh")
    assert get_chat_lang() == "zh"


def test_get_chat_lang_lang_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MMEM_LANG", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert get_chat_lang() == "en"
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert get_chat_lang() == "zh"
