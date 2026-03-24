"""记忆引擎后端封装：唯一从此模块直接 import pnms；业务与 CLI 应使用 ``PnmsMemoryBridge`` 的公开方法。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

import torch
from pnms import PNMS, PNMSClient, PNMSConfig, SimpleQueryEncoder

from mindmemory_client.memory_types import ChatTurnResult

LLMReasoner = Callable[[str, str], str]


def is_memory_engine_available() -> bool:
    """当前环境是否已安装可导入的 pnms 包。"""
    try:
        import pnms  # noqa: F401
        return True
    except ImportError:
        return False


def peek_checkpoint_version_info(checkpoint_dir: Path) -> dict[str, Any] | None:
    """读取 checkpoint 目录版本元数据；未安装 pnms 时返回 ``None``。"""
    try:
        from pnms import peek_checkpoint_versions

        return peek_checkpoint_versions(checkpoint_dir)
    except ImportError:
        return None


def _safe_segment(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return s[:200] if s else "default"


def resolve_pnms_data_dir(pnms_data_root: Path, user_uuid: str, agent_name: str) -> Path:
    """与 ``PnmsMemoryBridge`` 一致的目录：``{root}/{user}/{agent}/``。"""
    return Path(pnms_data_root) / _safe_segment(user_uuid) / _safe_segment(agent_name)


class _LocalPnmsClient(PNMSClient):
    """
    与 PNMSClient 相同，但 ``get_engine`` 时传入 SimpleQueryEncoder，
    避免默认 SentenceEncoder 触发 HuggingFace 下载。
    """

    def __init__(self, config: PNMSConfig) -> None:
        super().__init__(config)
        self._device = torch.device("cpu")
        self._encoder = SimpleQueryEncoder(embed_dim=config.embed_dim, vocab_size=10000)

    def get_engine(self, user_id: str) -> PNMS:
        if user_id not in self._engines:
            cfg = PNMSConfig.from_dict(self._base_config.to_dict())
            self._engines[user_id] = PNMS(
                config=cfg,
                user_id=user_id,
                encoder=self._encoder,
                device=self._device,
            )
        return self._engines[user_id]


class PnmsMemoryBridge:
    """
    为单个 (user_uuid, agent_name) 绑定 checkpoint 目录与逻辑 user_id ``{uuid}::{agent}``。

    对外请优先使用 ``handle_chat_turn`` / ``merge_external_checkpoint`` / ``persist_checkpoint``，
    避免依赖 ``.pnms``（保留仅为兼容旧代码）。
    """

    def __init__(
        self,
        pnms_data_root: Path,
        user_uuid: str,
        agent_name: str,
        pnms_config: PNMSConfig | None = None,
        *,
        checkpoint_dir: Path | None = None,
    ) -> None:
        self.user_uuid = user_uuid
        self.agent_name = agent_name
        self.user_id = f"{user_uuid}::{agent_name}"
        if checkpoint_dir is not None:
            root = Path(checkpoint_dir)
        else:
            from mindmemory_client.agent_workspace import agent_pnms_dir

            root = agent_pnms_dir(user_uuid, agent_name)
        root.mkdir(parents=True, exist_ok=True)
        base = pnms_config or PNMSConfig()
        cfg = PNMSConfig.from_dict(base.to_dict())
        cfg.concept_checkpoint_dir = str(root)
        self._client = _LocalPnmsClient(cfg)

    @property
    def pnms(self) -> PNMSClient:
        """底层多用户客户端（仅供库内遗留路径使用，新代码勿依赖）。"""
        return self._client

    def handle_chat_turn(
        self,
        query: str,
        llm: LLMReasoner,
        content_to_remember: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatTurnResult:
        """执行一轮对话并返回结构化结果（不暴露 pnms 类型）。"""
        r = self._client.handle(
            self.user_id,
            query,
            llm=llm,
            content_to_remember=content_to_remember,
            system_prompt=system_prompt,
        )
        return ChatTurnResult(
            response=r.response,
            context=r.context,
            num_slots_used=r.num_slots_used,
            phase=r.phase,
        )

    def merge_external_checkpoint(
        self,
        source_checkpoint_dir: str,
        source_memory_format_version: Optional[str] = None,
    ) -> dict[str, Any]:
        """将外部 checkpoint 目录并入当前引擎内存态，返回底层统计 dict。"""
        return self._client.merge(
            self.user_id,
            source_checkpoint_dir,
            source_memory_format_version=source_memory_format_version,
        )

    def save_checkpoint(self) -> None:
        self._client.get_engine(self.user_id).save_concept_modules()

    def persist_checkpoint(self) -> None:
        """与 ``save_checkpoint`` 相同，语义上强调「落盘」。"""
        self.save_checkpoint()

    def get_slot_count(self) -> int:
        return int(self._client.get_engine(self.user_id).store.num_slots)
