"""客户端环境变量：仅声明 ``MindMemoryClientConfig.from_env`` 实际消费的字段（其余 LLM/路径等由 ``get_env`` 直读）。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientEnvSettings(BaseSettings):
    """
    与 ``.env`` / ``os.environ`` 对齐（``get_client_settings()`` 前会先 ``ensure_dotenv_loaded()``）。

    说明：``MMEM_CLIENT_CONFIG_DIR`` / ``MMEM_ENV_FILE`` / LLM 相关等**不在此列出**，
    仍可通过环境变量或 ``.env`` 设置，由 ``client_paths`` / ``env_loader`` / ``llm_profiles`` 直接读取。
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    MMEM_BASE_URL: str | None = None
    MMEM_PNMS_DATA_ROOT: str | None = None
    MMEM_TIMEOUT_S: float | None = Field(default=None, description="HTTP 请求超时（秒）")

    MMEM_CREDENTIAL_SOURCE: str | None = Field(
        default=None,
        description="account | env | none",
    )
    MMEM_USER_UUID: str | None = None
    MMEM_PRIVATE_KEY_PATH: str | None = None


def get_client_settings() -> ClientEnvSettings:
    from mindmemory_client.env_loader import ensure_dotenv_loaded

    ensure_dotenv_loaded()
    return ClientEnvSettings()
