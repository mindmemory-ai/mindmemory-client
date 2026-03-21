"""LLM profile TOML 解析。"""

import textwrap
from pathlib import Path

import pytest

from mindmemory_client.env_loader import reset_dotenv_loaded
from mindmemory_client.llm_profiles import default_config_path, load_llm_profiles_from_toml


def test_load_array_form(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        textwrap.dedent(
            """
            [llm]
            default_profile = "fast"

            [[llm.profiles]]
            name = "default"
            backend = "ollama"
            ollama_model = "llama3.2"
            ollama_base_url = "http://127.0.0.1:11434"

            [[llm.profiles]]
            name = "fast"
            backend = "ollama"
            ollama_model = "phi3"
            ollama_base_url = "http://127.0.0.1:11434"
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = load_llm_profiles_from_toml(p)
    assert cfg.default_profile == "fast"
    assert cfg.profiles["fast"].ollama_model == "phi3"
    assert cfg.profiles["default"].ollama_model == "llama3.2"


def test_load_nested_table_form(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        textwrap.dedent(
            """
            [llm]
            default_profile = "a"

            [llm.profiles.a]
            backend = "ollama"
            ollama_model = "m1"
            ollama_base_url = "http://127.0.0.1:11434"

            [llm.profiles.b]
            ollama_model = "m2"
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = load_llm_profiles_from_toml(p)
    assert cfg.profiles["a"].ollama_model == "m1"
    assert cfg.profiles["b"].ollama_model == "m2"


def test_default_config_path_uses_client_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("MMEM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("MMEM_CONFIG_PATH", raising=False)
    root = tmp_path / "mm"
    root.mkdir()
    monkeypatch.setenv("MMEM_CLIENT_CONFIG_DIR", str(root))
    reset_dotenv_loaded()
    assert default_config_path() == root / "config.toml"
