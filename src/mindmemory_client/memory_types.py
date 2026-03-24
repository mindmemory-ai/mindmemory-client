"""记忆引擎对外数据结构（不依赖 pnms 类型名）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatTurnResult:
    """单轮对话的结构化结果（与底层引擎字段对齐，供 CLI / 集成方使用）。"""

    response: str
    context: str
    num_slots_used: int
    phase: str
