"""LLM 多模型配置：默认 Ollama；配置文件 ~/.mindmemory/config.toml（或 MMEM_CONFIG_PATH）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mindmemory_client.client_paths import client_config_dir
from mindmemory_client.env_loader import get_env


def default_config_path() -> Path:
    p = get_env("MMEM_CONFIG_PATH")
    if p:
        return Path(p).expanduser()
    return client_config_dir() / "config.toml"


class LlmProfile(BaseModel):
    """单个大模型配置（命名 profile）。"""

    backend: Literal["ollama", "mock", "echo", "openai_chat"] = "ollama"
    """``ollama``：Ollama ``/api/chat``；``openai_chat``：OpenAI 兼容 ``/v1/chat/completions``。"""
    target: Literal["local", "remote"] = "local"
    """local：默认本机 11434；remote：自定义 URL，可配 api_token。"""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    """Ollama 模型名；``backend=openai_chat`` 时作为 Chat Completions 的 ``model``。"""
    openai_base_url: str = "https://api.openai.com/v1"
    """``backend=openai_chat`` 时 API 根路径（含 ``/v1``）。"""
    api_token: str | None = None
    """Bearer；Ollama 远程或 OpenAI / 兼容网关。"""
    timeout_s: float = 120.0


class LlmProfilesConfig(BaseModel):
    default_profile: str = "default"
    profiles: dict[str, LlmProfile] = Field(default_factory=dict)


def _builtin() -> LlmProfilesConfig:
    return LlmProfilesConfig(
        default_profile="default",
        profiles={"default": LlmProfile()},
    )


def _profile_from_mapping(item: dict, defaults: LlmProfile) -> LlmProfile:
    return LlmProfile(
        backend=item.get("backend", defaults.backend),
        target=item.get("target", defaults.target),
        ollama_base_url=str(item.get("ollama_base_url", defaults.ollama_base_url)),
        ollama_model=str(item.get("ollama_model", defaults.ollama_model)),
        openai_base_url=str(item.get("openai_base_url", defaults.openai_base_url)),
        api_token=item.get("api_token") if item.get("api_token") else None,
        timeout_s=float(item.get("timeout_s", defaults.timeout_s)),
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
    d0 = LlmProfile()

    raw = llm.get("profiles")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            profiles[str(name)] = _profile_from_mapping(item, d0)
    elif isinstance(raw, dict):
        for name, body in raw.items():
            if not isinstance(body, dict):
                continue
            profiles[str(name)] = _profile_from_mapping(body, d0)

    if not profiles:
        return base
    return LlmProfilesConfig(default_profile=default_name, profiles=profiles)


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if v is None:
        return '""'
    return json.dumps(str(v), ensure_ascii=False)


def write_llm_profiles_to_toml(path: Path, cfg: LlmProfilesConfig) -> None:
    """将完整 ``LlmProfilesConfig`` 写入 TOML（数组形式 ``[[llm.profiles]]``）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# MindMemory 客户端 LLM 配置（mmem models configure 可写入）",
        "",
        "[llm]",
        f'default_profile = {_toml_value(cfg.default_profile)}',
        "",
    ]
    for name in sorted(cfg.profiles.keys()):
        p = cfg.profiles[name]
        lines.append("[[llm.profiles]]")
        lines.append(f'name = {_toml_value(name)}')
        lines.append(f'backend = {_toml_value(p.backend)}')
        lines.append(f'target = {_toml_value(p.target)}')
        lines.append(f'ollama_base_url = {_toml_value(p.ollama_base_url)}')
        lines.append(f'ollama_model = {_toml_value(p.ollama_model)}')
        if p.backend == "openai_chat":
            lines.append(f'openai_base_url = {_toml_value(p.openai_base_url)}')
        if p.api_token:
            lines.append(f'api_token = {_toml_value(p.api_token)}')
        lines.append(f'timeout_s = {_toml_value(p.timeout_s)}')
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def upsert_llm_profile(
    path: Path | None,
    profile_name: str,
    profile: LlmProfile,
    *,
    set_default: bool = False,
) -> LlmProfilesConfig:
    """加载已有文件或新建，合并指定 profile 后写入 ``path``（默认 ``default_config_path()``）。"""
    file_path = path or default_config_path()
    if file_path.is_file():
        base = load_llm_profiles_from_toml(file_path)
    else:
        base = LlmProfilesConfig(default_profile=profile_name, profiles={})
    base.profiles[profile_name] = profile
    if set_default:
        base.default_profile = profile_name
    write_llm_profiles_to_toml(file_path, base)
    return base


def resolve_profile(
    cfg: LlmProfilesConfig,
    profile_name: str | None,
    *,
    ollama_url_override: str | None = None,
    ollama_model_override: str | None = None,
) -> LlmProfile:
    """选取 profile。覆盖优先级：CLI > 环境变量 > 文件 > 内置。"""
    name = profile_name or get_env("MMEM_LLM_PROFILE") or cfg.default_profile
    prof = cfg.profiles.get(name)
    if prof is None:
        prof = cfg.profiles.get("default") or LlmProfile()

    d = prof.model_dump()
    if get_env("MMEM_OLLAMA_URL"):
        d["ollama_base_url"] = get_env("MMEM_OLLAMA_URL")
    if get_env("MMEM_OLLAMA_MODEL"):
        d["ollama_model"] = get_env("MMEM_OLLAMA_MODEL")
    tok = get_env("MMEM_OLLAMA_API_TOKEN")
    if tok is not None and str(tok).strip() != "":
        d["api_token"] = str(tok).strip()
    if ollama_url_override:
        d["ollama_base_url"] = ollama_url_override
    if ollama_model_override:
        d["ollama_model"] = ollama_model_override
    if get_env("OPENAI_BASE_URL"):
        d["openai_base_url"] = str(get_env("OPENAI_BASE_URL")).strip()
    tok_oai = get_env("OPENAI_API_KEY")
    out = LlmProfile.model_validate(d)
    if out.backend == "openai_chat" and tok_oai and str(tok_oai).strip():
        out = out.model_copy(update={"api_token": str(tok_oai).strip()})
    return out


def effective_ollama_url(profile: LlmProfile) -> str:
    """按 target 解析最终请求 URL（local 未显式改 URL 时保持本机）。"""
    u = profile.ollama_base_url.strip()
    if profile.target == "local" and not u:
        return "http://127.0.0.1:11434"
    return u or "http://127.0.0.1:11434"
