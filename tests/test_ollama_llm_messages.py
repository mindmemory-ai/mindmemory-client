"""Ollama：system + user 消息结构。"""

from unittest.mock import MagicMock, patch

from mindmemory_client.llm_profiles import LlmProfile
from mindmemory_client.ollama_llm import build_ollama_llm


def _minimal_profile() -> LlmProfile:
    return LlmProfile(ollama_model="test-model")


@patch("mindmemory_client.ollama_llm.httpx.Client")
def test_build_ollama_llm_posts_system_and_user(mock_client_cls: MagicMock) -> None:
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {"message": {"content": "ok"}}

    mock_client = MagicMock()
    mock_client.post.return_value = resp_ok
    mock_client_cls.return_value = mock_client

    prof = _minimal_profile()
    llm = build_ollama_llm(prof, workspace_block="[id]\nhello", lang="zh")
    out = llm("q1", "ctx-from-pnms")
    assert out == "ok"

    mock_client.post.assert_called_once()
    call_kw = mock_client.post.call_args
    body = call_kw[1]["json"]
    msgs = body["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "hello" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "ctx-from-pnms" in msgs[1]["content"]
    assert "q1" in msgs[1]["content"]


@patch("mindmemory_client.ollama_llm.httpx.Client")
def test_build_ollama_llm_no_workspace_single_system(mock_client_cls: MagicMock) -> None:
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {"message": {"content": "x"}}

    mock_client = MagicMock()
    mock_client.post.return_value = resp_ok
    mock_client_cls.return_value = mock_client

    prof = _minimal_profile()
    llm = build_ollama_llm(prof, workspace_block=None, lang="en")
    llm("q", "ctx")

    body = mock_client.post.call_args[1]["json"]
    msgs = body["messages"]
    assert msgs[0]["role"] == "system"
    assert "[id]" not in msgs[0]["content"]
