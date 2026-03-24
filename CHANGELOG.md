# Changelog

本文件遵循语义化版本（MAJOR.MINOR.PATCH），与 `pyproject.toml` 的 `version` 对齐。

## [0.2.0] — 2026-03-24

### Added

- **库**：`read_extras_enc_text_block`、`merge_workspace_prompt_and_extras`：按 [memory-repo-extended-layout §6](docs/memory-repo-extended-layout.md) 将 **`extras.enc` 解密片段**与 **`prompt`** 明文合并为工作区块。
- **`mmem chat`**：**`--chat-extras`** / **`MMEM_CHAT_INCLUDE_EXTRAS=1`**：从 Agent **`repo/mmem/bundles/extras.enc`** 解密并拼入 LLM 工作区上下文（需 **`K_seed`**，即已配置私钥）。
- **`mmem chat`**：`--llm openai` 或 profile `backend = "openai_chat"`，OpenAI 兼容 `POST /v1/chat/completions`。
- **`mmem chat`**：`--verbose` / `MMEM_CHAT_DEBUG=1`；同步/合并 Git 失败时的可操作提示。
- **测试**：`tests/test_openai_chat_llm.py`、`tests/test_cli_mmem.py`、pytest 标记 **`e2e_remote`**。

### Documentation

- **README**：区分**最小安装**（仅本库）与**完整能力**（`pnms` + 可选 `torch`）。

## [0.1.0]

初始发布：`mindmemory_client` + **`mmem`** CLI（PNMS 桥接、MMEM API、workspace / sync / extras 等）。
