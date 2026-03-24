"""OpenAI Chat Completions 兼容 HTTP（含多数「OpenAI 兼容」网关）：``/v1/chat/completions``。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import httpx

from mindmemory_client.chat_strings import chat_strings
from mindmemory_client.llm_profiles import LlmProfile
from mindmemory_client.ollama_llm import write_prompt_dump_file

logger = logging.getLogger(__name__)


def _headers(profile: LlmProfile) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if profile.api_token and profile.api_token.strip():
        h["Authorization"] = f"Bearer {profile.api_token.strip()}"
    return h


def build_openai_chat_llm(
    profile: LlmProfile,
    workspace_block: str | None = None,
    *,
    lang: str = "zh",
    dump_prompt_path: Path | None = None,
    dump_append: bool = False,
) -> Callable[[str, str], str]:
    """
    ``(query, context) -> response``；请求 **POST** ``{openai_base_url}/chat/completions``。

    模型名使用 profile 的 **``ollama_model``** 字段（与配置共用「模型 id」槽位，避免再增字段）。
    """
    base = profile.openai_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    headers = _headers(profile)
    client = httpx.Client(timeout=profile.timeout_s, headers=headers)
    s = chat_strings(lang)
    system_intro = str(s["ollama_system_intro"])
    if workspace_block and workspace_block.strip():
        system_content = system_intro + "\n\n---\n\n" + workspace_block.strip()
    else:
        system_content = system_intro

    def llm(query: str, context: str) -> str:
        user_content = (
            str(s["ollama_user_memory_prefix"])
            + context
            + str(s["ollama_user_memory_suffix"])
            + query
        )
        if dump_prompt_path is not None:
            try:
                dump_text = (
                    "[role: system]\n"
                    + system_content
                    + "\n\n[role: user]\n"
                    + user_content
                    + "\n"
                )
                write_prompt_dump_file(dump_prompt_path, dump_text, append=dump_append)
            except OSError as e:
                logger.warning("prompt dump write failed: %s", e)

        body: dict[str, Any] = {
            "model": profile.ollama_model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
        }
        logger.debug(
            "OpenAI chat model=%s url=%s query_chars=%d context_chars=%d",
            profile.ollama_model,
            url,
            len(query),
            len(context),
        )
        r = client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenAI 兼容响应无 choices: {data!r}")
        msg = choices[0].get("message") or {}
        text = msg.get("content")
        if not text:
            raise RuntimeError(f"OpenAI 兼容响应无 content: {data!r}")
        return str(text)

    return llm
