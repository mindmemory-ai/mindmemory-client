"""Ollama 非流式调用：优先 ``/api/chat``，404 时回退 ``/api/generate``（兼容旧版无 Chat API 的实例）。"""

from __future__ import annotations

import logging
from typing import Callable

import httpx

from mindmemory_client.llm_profiles import LlmProfile

logger = logging.getLogger(__name__)


def _ollama_error_detail(resp: httpx.Response) -> str:
    try:
        j = resp.json()
        if isinstance(j, dict) and j.get("error"):
            return str(j["error"])
    except Exception:
        pass
    t = (resp.text or "").strip()
    return t[:400] if t else f"HTTP {resp.status_code} 无响应体"


def build_ollama_llm(profile: LlmProfile) -> Callable[[str, str], str]:
    base = profile.ollama_base_url.rstrip("/")
    client = httpx.Client(timeout=profile.timeout_s)

    def llm(query: str, context: str) -> str:
        # PNMS 传入的 context 已含系统与记忆；再拼用户问题
        user_content = (
            f"以下是与记忆相关的上下文：\n{context}\n\n请根据上下文回答。\n用户问题：{query}"
        )
        logger.debug(
            "Ollama request model=%s base=%s query_chars=%d context_chars=%d",
            profile.ollama_model,
            base,
            len(query),
            len(context),
        )
        body_chat = {
            "model": profile.ollama_model,
            "messages": [{"role": "user", "content": user_content}],
            "stream": False,
        }
        r = client.post(f"{base}/api/chat", json=body_chat)
        if r.status_code == 200:
            data = r.json()
            msg = data.get("message") or {}
            text = msg.get("content")
            if not text:
                raise RuntimeError(f"Ollama 响应异常: {data!r}")
            return str(text)

        if r.status_code != 404:
            r.raise_for_status()

        # /api/chat 返回 404：多为旧版无 Chat API；也可能是模型不存在（/api/generate 会同样失败）
        body_gen = {
            "model": profile.ollama_model,
            "prompt": user_content,
            "stream": False,
        }
        r2 = client.post(f"{base}/api/generate", json=body_gen)
        if r2.status_code == 200:
            data2 = r2.json()
            text2 = data2.get("response")
            if not text2:
                raise RuntimeError(f"Ollama /api/generate 响应异常: {data2!r}")
            return str(text2)

        raise RuntimeError(
            f"Ollama 不可用（model={profile.ollama_model!r}，base={base}）。"
            f"/api/chat → HTTP {r.status_code}: {_ollama_error_detail(r)}；"
            f"/api/generate → HTTP {r2.status_code}: {_ollama_error_detail(r2)}。"
            "常见原因：① 未拉取模型，请执行 `ollama pull <模型名>` 后重试；"
            "② 模型名与 `ollama list` 中完全一致（含 tag，如 `llama3.2:latest`）；"
            "③ 确认 `MMEM_OLLAMA_URL` / `config.toml` 指向正在监听的 Ollama（默认 http://127.0.0.1:11434），"
            "且本机无其它进程占用该端口。"
        )

    return llm


def ollama_health(base_url: str, timeout: float = 5.0) -> dict:
    """GET /api/tags，用于 doctor。"""
    base = base_url.rstrip("/")
    r = httpx.get(f"{base}/api/tags", timeout=timeout)
    r.raise_for_status()
    return r.json()
