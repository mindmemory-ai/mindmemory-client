"""Ollama：system + user 消息结构与 prompt dump。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from mindmemory_client.llm_profiles import LlmProfile
from mindmemory_client.ollama_llm import build_ollama_llm, write_prompt_dump_file


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


@patch("mindmemory_client.ollama_llm.httpx.Client")
def test_build_ollama_llm_writes_prompt_dump(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {"message": {"content": "ok"}}

    mock_client = MagicMock()
    mock_client.post.return_value = resp_ok
    mock_client_cls.return_value = mock_client

    dump = tmp_path / "p.txt"
    prof = _minimal_profile()
    llm = build_ollama_llm(
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


def test_write_prompt_dump_file_append(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    write_prompt_dump_file(p, "one", append=False)
    assert p.read_text(encoding="utf-8") == "one"
    write_prompt_dump_file(p, "two", append=True)
    assert "one" in p.read_text(encoding="utf-8")
    assert "two" in p.read_text(encoding="utf-8")
