from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


def _env(name: str, default: str | None = None) -> str | None:
    import os

    return os.environ.get(name, default)


class MindMemoryClientConfig(BaseModel):
    """客户端配置（可与环境变量合并使用）。"""

    base_url: str = Field(
        default_factory=lambda: _env("MMEM_BASE_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000",
        description="MindMemory 服务根 URL（不含 /api/v1）",
    )
    user_uuid: str | None = Field(default_factory=lambda: _env("MMEM_USER_UUID"))
    private_key_path: Path | None = Field(
        default_factory=lambda: Path(p) if (p := _env("MMEM_PRIVATE_KEY_PATH")) else None
    )
    pnms_data_root: Path = Field(
        default_factory=lambda: Path(
            _env("MMEM_PNMS_DATA_ROOT", str(Path.home() / ".cache" / "mmem" / "pnms"))
        )
    )
    timeout_s: float = Field(default=60.0)
    agent_name: str = Field(default="cli-agent", description="默认 Agent 名称，对应 MMEM 与 PNMS 隔离")

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_env(cls) -> MindMemoryClientConfig:
        return cls()
