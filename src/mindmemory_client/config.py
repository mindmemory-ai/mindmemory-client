from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mindmemory_client.client_paths import client_data_dir
from mindmemory_client.credential_source import credential_source

DEFAULT_AGENT_NAME = "BT-7274"


class MindMemoryClientConfig(BaseModel):
    """客户端配置：由 ``from_env()`` 解析。"""

    base_url: str = Field(
        default="http://127.0.0.1:8000",
        description="MindMemory 服务根 URL（不含 /api/v1）",
    )
    user_uuid: str | None = Field(default=None)
    private_key_path: Path | None = Field(default=None)
    pnms_data_root: Path = Field(
        default_factory=client_data_dir,
        description="兼容字段；PNMS checkpoint 实际路径见账号下 agents/<agent>/pnms",
    )
    timeout_s: float = Field(default=60.0)
    agent_name: str = Field(
        default=DEFAULT_AGENT_NAME,
        description="默认 Agent 名称，对应 MMEM 与 PNMS 隔离",
    )

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_env(cls) -> MindMemoryClientConfig:
        from mindmemory_client.settings import get_client_settings

        s = get_client_settings()
        src = credential_source()
        uid: str | None = None
        pk: Path | None = None
        if src == "env":
            uid = s.MMEM_USER_UUID
            if s.MMEM_PRIVATE_KEY_PATH:
                pk = Path(s.MMEM_PRIVATE_KEY_PATH).expanduser()
        pnms = s.MMEM_PNMS_DATA_ROOT
        to = s.MMEM_TIMEOUT_S
        return cls(
            base_url=(s.MMEM_BASE_URL or "http://127.0.0.1:8000"),
            user_uuid=uid,
            private_key_path=pk,
            pnms_data_root=Path(pnms or str(client_data_dir())).expanduser(),
            timeout_s=float(to) if to is not None else 60.0,
            agent_name=DEFAULT_AGENT_NAME,
        )
