"""LLM 多模型配置：默认 Ollama；配置文件 ~/.config/mmem/config.toml（或 MMEM_CONFIG_PATH）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def default_config_path() -> Path:
    p = _env("MMEM_CONFIG_PATH")
    if p:
        return Path(p).expanduser()
    return Path.home() / ".config" / "mmem" / "config.toml"


class LlmProfile(BaseModel):
    """单个大模型配置（命名 profile）。"""

    backend: Literal["ollama", "mock", "echo"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    timeout_s: float = 120.0


class LlmProfilesConfig(BaseModel):
    default_profile: str = "default"
    profiles: dict[str, LlmProfile] = Field(default_factory=dict)


def _builtin() -> LlmProfilesConfig:
    return LlmProfilesConfig(
        default_profile="default",
        profiles={"default": LlmProfile()},
    )


def load_llm_profiles_from_toml(path: Path | None) -> LlmProfilesConfig:
    """读取 TOML；文件不存在则返回内置 default（ollama llama3.2）。"""
    base = _builtin()
    file_path = path or default_config_path()
    if not file_path.is_file():
        return base
    import tomllib

    data = tomllib.loads(file_path.read_text(encoding="utf-8"))
    llm = data.get("llm") or {}
    default_name = str(llm.get("default_profile", base.default_profile))
    profiles: dict[str, LlmProfile] = {}

    raw = llm.get("profiles")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            profiles[str(name)] = LlmProfile(
                backend=item.get("backend", "ollama"),
                ollama_base_url=str(
                    item.get("ollama_base_url", LlmProfile().ollama_base_url)
                ),
                ollama_model=str(item.get("ollama_model", LlmProfile().ollama_model)),
                timeout_s=float(item.get("timeout_s", 120.0)),
            )
    elif isinstance(raw, dict):
        for name, body in raw.items():
            if not isinstance(body, dict):
                continue
            profiles[str(name)] = LlmProfile(
                backend=body.get("backend", "ollama"),
                ollama_base_url=str(body.get("ollama_base_url", LlmProfile().ollama_base_url)),
                ollama_model=str(body.get("ollama_model", LlmProfile().ollama_model)),
                timeout_s=float(body.get("timeout_s", 120.0)),
            )

    if not profiles:
        return base
    return LlmProfilesConfig(default_profile=default_name, profiles=profiles)


def resolve_profile(
    cfg: LlmProfilesConfig,
    profile_name: str | None,
    *,
    ollama_url_override: str | None = None,
    ollama_model_override: str | None = None,
) -> LlmProfile:
    """选取 profile。覆盖优先级：CLI > 环境变量 > 文件 > 内置。"""
    name = profile_name or _env("MMEM_LLM_PROFILE") or cfg.default_profile
    prof = cfg.profiles.get(name)
    if prof is None:
        prof = cfg.profiles.get("default") or LlmProfile()

    d = prof.model_dump()
    if _env("MMEM_OLLAMA_URL"):
        d["ollama_base_url"] = _env("MMEM_OLLAMA_URL")
    if _env("MMEM_OLLAMA_MODEL"):
        d["ollama_model"] = _env("MMEM_OLLAMA_MODEL")
    if ollama_url_override:
        d["ollama_base_url"] = ollama_url_override
    if ollama_model_override:
        d["ollama_model"] = ollama_model_override
    return LlmProfile.model_validate(d)
