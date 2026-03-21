"""PNMS 封装：按 user_uuid + agent_name 隔离数据目录；默认 SimpleQueryEncoder 避免首次联网拉模型。"""

from __future__ import annotations

import re
from pathlib import Path

import torch
from pnms import PNMS, PNMSClient, PNMSConfig, SimpleQueryEncoder


def _safe_segment(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return s[:200] if s else "default"


def resolve_pnms_data_dir(pnms_data_root: Path, user_uuid: str, agent_name: str) -> Path:
    """与 PnmsMemoryBridge 一致的 PNMS 数据目录：``{root}/{user}/{agent}/``。"""
    return Path(pnms_data_root) / _safe_segment(user_uuid) / _safe_segment(agent_name)


class _LocalPnmsClient(PNMSClient):
    """
    与 PNMSClient 相同，但 get_engine 时传入 SimpleQueryEncoder，
    避免默认 SentenceEncoder 触发 HuggingFace 下载（CLI/测试离线可用）。
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
    为单个 (user_uuid, agent_name) 创建独立 concept_checkpoint_dir，
    PNMS 逻辑 user_id 为 ``{user_uuid}::{agent_name}``。
    """

    def __init__(
        self,
        pnms_data_root: Path,
        user_uuid: str,
        agent_name: str,
        pnms_config: PNMSConfig | None = None,
    ) -> None:
        self.user_uuid = user_uuid
        self.agent_name = agent_name
        self.user_id = f"{user_uuid}::{agent_name}"
        root = resolve_pnms_data_dir(Path(pnms_data_root), user_uuid, agent_name)
        root.mkdir(parents=True, exist_ok=True)
        base = pnms_config or PNMSConfig()
        cfg = PNMSConfig.from_dict(base.to_dict())
        cfg.concept_checkpoint_dir = str(root)
        self._client = _LocalPnmsClient(cfg)

    @property
    def pnms(self) -> PNMSClient:
        return self._client

    def save_checkpoint(self) -> None:
        self._client.get_engine(self.user_id).save_concept_modules()
