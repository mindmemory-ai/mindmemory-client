"""单会话：一轮对话中记忆引擎 handle + 默认记忆摘要。"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from mindmemory_client.memory_types import ChatTurnResult
from mindmemory_client.pnms_bridge import LLMReasoner, PnmsMemoryBridge

logger = logging.getLogger(__name__)


class ChatMemorySession:
    """将用户 query、LLM 回调与可选巩固文本交给记忆引擎。"""

    def __init__(
        self,
        bridge: PnmsMemoryBridge,
        system_prompt: str = "你是个人助手，请严格依据记忆回答。",
    ) -> None:
        self._bridge = bridge
        self.system_prompt = system_prompt

    @property
    def user_id(self) -> str:
        return self._bridge.user_id

    def handle_turn(
        self,
        query: str,
        llm: LLMReasoner,
        content_to_remember: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatTurnResult:
        if content_to_remember is None:
            content_to_remember = f"[对话轮次] 用户：{query[:2000]}"
        sp = system_prompt if system_prompt is not None else self.system_prompt
        logger.info(
            "chat turn user=%s query_chars=%d",
            self._bridge.user_id,
            len(query),
        )
        return self._bridge.handle_chat_turn(
            query,
            llm,
            content_to_remember=content_to_remember,
            system_prompt=sp,
        )

    def save_checkpoint(self) -> None:
        self._bridge.save_checkpoint()
