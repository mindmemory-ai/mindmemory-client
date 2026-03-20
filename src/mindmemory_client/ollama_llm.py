"""Ollama /api/chat 非流式调用，签名 (query, context) -> str 供 PNMS 使用。"""

from __future__ import annotations

from typing import Callable

import httpx

from mindmemory_client.llm_profiles import LlmProfile


def build_ollama_llm(profile: LlmProfile) -> Callable[[str, str], str]:
    base = profile.ollama_base_url.rstrip("/")
    client = httpx.Client(timeout=profile.timeout_s)

    def llm(query: str, context: str) -> str:
        # PNMS 传入的 context 已含系统与记忆；再拼用户问题
        user_content = (
            f"以下是与记忆相关的上下文：\n{context}\n\n请根据上下文回答。\n用户问题：{query}"
        )
        body = {
            "model": profile.ollama_model,
            "messages": [{"role": "user", "content": user_content}],
            "stream": False,
        }
        r = client.post(f"{base}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message") or {}
        text = msg.get("content")
        if not text:
            raise RuntimeError(f"Ollama 响应异常: {data!r}")
        return str(text)

    return llm


def ollama_health(base_url: str, timeout: float = 5.0) -> dict:
    """GET /api/tags，用于 doctor。"""
    base = base_url.rstrip("/")
    r = httpx.get(f"{base}/api/tags", timeout=timeout)
    r.raise_for_status()
    return r.json()
