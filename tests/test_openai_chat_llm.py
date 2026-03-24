"""OpenAI 兼容 Chat Completions：请求体与 prompt dump。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from mindmemory_client.llm_profiles import LlmProfile
from mindmemory_client.openai_chat_llm import build_openai_chat_llm


def _openai_profile() -> LlmProfile:
    return LlmProfile(
        backend="openai_chat",
        ollama_model="gpt-4o-mini",
        openai_base_url="https://api.example.com/v1",
        api_token="test-token",
    )


@patch("mindmemory_client.openai_chat_llm.httpx.Client")
def test_build_openai_chat_llm_posts_system_and_user(mock_client_cls: MagicMock) -> None:
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.raise_for_status = MagicMock()
    resp_ok.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    mock_client = MagicMock()
    mock_client.post.return_value = resp_ok
    mock_client_cls.return_value = mock_client

    prof = _openai_profile()
    llm = build_openai_chat_llm(prof, workspace_block="[id]\nhello", lang="zh")
    out = llm("q1", "ctx-from-pnms")
    assert out == "ok"

    mock_client.post.assert_called_once()
    call_kw = mock_client.post.call_args
    assert call_kw[0][0] == "https://api.example.com/v1/chat/completions"
    body = call_kw[1]["json"]
    msgs = body["messages"]
    assert body["model"] == "gpt-4o-mini"
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "hello" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "ctx-from-pnms" in msgs[1]["content"]
    assert "q1" in msgs[1]["content"]

    hdrs = mock_client_cls.call_args[1]["headers"]
    assert hdrs["Authorization"] == "Bearer test-token"


@patch("mindmemory_client.openai_chat_llm.httpx.Client")
def test_build_openai_chat_llm_writes_prompt_dump(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.raise_for_status = MagicMock()
    resp_ok.json.return_value = {"choices": [{"message": {"content": "x"}}]}

    mock_client = MagicMock()
    mock_client.post.return_value = resp_ok
    mock_client_cls.return_value = mock_client

    dump = tmp_path / "p.txt"
    prof = _openai_profile()
    llm = build_openai_chat_llm(
        prof,
        workspace_block="ws",
        lang="zh",
        dump_prompt_path=dump,
        dump_append=False,
    )
    llm("q1", "ctx1")
    text = dump.read_text(encoding="utf-8")
    assert "[role: system]" in text
    assert "[role: user]" in text
    assert "ctx1" in text
    assert "q1" in text
    assert "ws" in text
