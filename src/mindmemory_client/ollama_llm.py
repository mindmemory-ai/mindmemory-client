"""Ollama 非流式调用：优先 ``/api/chat``，404 时回退 ``/api/generate``（兼容旧版无 Chat API 的实例）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import httpx

from mindmemory_client.chat_strings import chat_strings
from mindmemory_client.llm_profiles import LlmProfile, effective_ollama_url

logger = logging.getLogger(__name__)


def write_prompt_dump_file(path: Path, text: str, *, append: bool) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    need_sep = append and path.is_file() and path.stat().st_size > 0
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as f:
        if need_sep:
            f.write("\n\n" + "=" * 72 + "\n\n")
        f.write(text)


def _ollama_headers(profile: LlmProfile) -> dict[str, str]:
    h: dict[str, str] = {}
    if profile.api_token and profile.api_token.strip():
        h["Authorization"] = f"Bearer {profile.api_token.strip()}"
    return h


def _ollama_error_detail(resp: httpx.Response) -> str:
    try:
        j = resp.json()
        if isinstance(j, dict) and j.get("error"):
            return str(j["error"])
    except Exception:
        pass
    t = (resp.text or "").strip()
    return t[:400] if t else f"HTTP {resp.status_code} 无响应体"


def build_ollama_llm(
    profile: LlmProfile,
    workspace_block: str | None = None,
    *,
    lang: str = "zh",
    dump_prompt_path: Path | None = None,
    dump_append: bool = False,
) -> Callable[[str, str], str]:
    """
    构造 ``(query, context) -> response``；向 Ollama 发送 **system**（说明 + 可选工作区人格）与 **user**（PNMS 上下文 + 问题）。

    ``context`` 为 PNMS ``context_builder`` 输出（已含简短 ``system_prompt``）；``workspace_block`` 单独进入 **system**，避免与记忆检索串挤在同一条 user 里。
    """
    base = effective_ollama_url(profile).rstrip("/")
    headers = _ollama_headers(profile)
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
        logger.debug(
            "Ollama request model=%s base=%s query_chars=%d context_chars=%d auth=%s",
            profile.ollama_model,
            base,
            len(query),
            len(context),
            bool(headers),
        )
        body_chat: dict[str, Any] = {
            "model": profile.ollama_model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
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
        prompt_legacy = f"[System]\n{system_content}\n\n[User]\n{user_content}"
        body_gen: dict[str, Any] = {
            "model": profile.ollama_model,
            "prompt": prompt_legacy,
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
            "③ 确认 URL / `config.toml` 指向正在监听的 Ollama，"
            "且本机无其它进程占用该端口；远程需检查 api_token。"
        )

    return llm


def ollama_health(base_url: str, timeout: float = 5.0, *, headers: dict[str, str] | None = None) -> dict:
    """GET /api/tags，用于 doctor / mmem models tags。"""
    base = base_url.rstrip("/")
    r = httpx.get(f"{base}/api/tags", timeout=timeout, headers=headers or {})
    r.raise_for_status()
    return r.json()
