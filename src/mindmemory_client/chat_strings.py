"""mmem chat 文案：默认中文，可通过 ``MMEM_LANG`` / ``LANG`` 切换英文。"""

from __future__ import annotations

import os
from typing import Any


def get_chat_lang() -> str:
    """返回 ``zh`` 或 ``en``。"""
    v = (os.environ.get("MMEM_LANG") or "").strip().lower()
    if v in ("en", "english", "en_us", "en-us"):
        return "en"
    if v in ("zh", "zh-cn", "chinese", "zh_cn", "zh-hans"):
        return "zh"
    lang = (os.environ.get("LANG") or "C").lower()
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    return "zh"


def chat_strings(lang: str | None = None) -> dict[str, Any]:
    """当前语言的键值表；未知语言回退 ``zh``。"""
    l = (lang or get_chat_lang()).lower()
    if l not in _TABLE:
        l = "zh"
    return _TABLE[l]


_TABLE: dict[str, dict[str, Any]] = {
    "zh": {
        "session_system_default": "你是个人助手，请严格依据记忆回答。",
        "ollama_system_intro": (
            "你是协助用户的助手。用户消息中的「与记忆相关的上下文」来自神经记忆引擎检索结果；"
            "请严格依据该上下文与用户问题作答。若上文另有「工作区」身份/人格设定，在不相悖的前提下融入语气。"
        ),
        "ollama_user_memory_prefix": "以下是与记忆相关的上下文：\n",
        "ollama_user_memory_suffix": "\n\n请根据上下文回答。\n用户问题：",
        "status_workspace_skipped": (
            "工作区提示：已跳过 mmem-workspace.json（--no-workspace-prompt 或 MMEM_CHAT_NO_WORKSPACE_PROMPT）。"
        ),
        "status_workspace_loaded": "工作区提示：已加载 workspace/mmem-workspace.json 的 prompt 段（将单独作为 system 传给 Ollama）。",
        "status_workspace_missing": "工作区提示：未找到 mmem-workspace.json，仅使用默认系统提示。",
        "status_workspace_no_prompt": "工作区提示：已找到 mmem-workspace.json，但未配置 prompt 或无可读文件。",
        "status_workspace_errors": "工作区提示：解析或读取存在问题 — {details}",
    },
    "en": {
        "session_system_default": "You are a helpful assistant; answer strictly based on memory context when provided.",
        "ollama_system_intro": (
            "You assist the user. The user message contains “context related to memory” from the neural memory engine; "
            "answer using that context and the user's question. If a separate workspace persona/identity block is provided "
            "above, align tone when it does not conflict with safety or facts."
        ),
        "ollama_user_memory_prefix": "Context related to memory:\n",
        "ollama_user_memory_suffix": "\n\nAnswer using the context above.\nUser question: ",
        "status_workspace_skipped": (
            "Workspace: skipped mmem-workspace.json (--no-workspace-prompt or MMEM_CHAT_NO_WORKSPACE_PROMPT)."
        ),
        "status_workspace_loaded": "Workspace: loaded prompt section from mmem-workspace.json (sent as Ollama system).",
        "status_workspace_missing": "Workspace: mmem-workspace.json not found; using default system prompt only.",
        "status_workspace_no_prompt": "Workspace: mmem-workspace.json exists but has no prompt or no readable files.",
        "status_workspace_errors": "Workspace: issues while parsing/reading — {details}",
    },
}
