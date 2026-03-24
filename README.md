# mindmemory-client

Python 库与官方示例 CLI **`mmem`**：长期记忆（由 `pnms` 提供实现，**仅**在库内 `pnms_bridge` 等模块引用）+ MindMemory `/api/v1`（含 sync 签名）。**CLI 与业务集成应通过 `mindmemory_client` 公开 API，不要直接 `import pnms`。**

## 安装层次

| 范围 | 命令 | 能力 |
|------|------|------|
| **最小** | `pip install -e .`（或自 PyPI 安装发布后包） | 配置、HTTP API 客户端、同步签名、workspace/extras **库 API** 等；**不含**可运行的神经记忆引擎。 |
| **完整（开发）** | 先 `pip install -e ../pnms` 再 `pip install -e ".[dev]"` | **`mmem chat`**、**`mmem doctor`** 中的 PNMS 检查、与 checkpoint 相关的集成测试；`pnms` 依赖 **`torch`** 等，体积较大。 |

开发调试建议始终使用「完整」一行，与仓库 `TODO.md` 一致：

```bash
pip install -e ../pnms
pip install -e ".[dev]"
```

设计见 `docs/mindmemory-client-设计.md`；安装与 CLI 用法见 `docs/mmem-使用说明.md`；版本变更见 **`CHANGELOG.md`**。环境变量可通过 **`~/.mindmemory/.env`** 或 **`cwd/.env`** 配置（模板见 `.env.example`）。多账户场景保持 **`MMEM_CREDENTIAL_SOURCE=account`**（默认），勿在 `.env` 写死 `MMEM_USER_UUID`/`MMEM_PRIVATE_KEY_PATH`；脚本身份用 **`MMEM_CREDENTIAL_SOURCE=env`**。

**同步**：`mmem sync push` 向 Git 提交加密后的 **`pnms_bundle.enc`**（本地 checkpoint 目录打包）。推送前会 `git fetch` 并与远端比较；若远端较新或分叉，请先 **`mmem memory merge`**。需要把远端 bundle 合入本地时，使用 **`mmem memory import-bundle`** 或 **`mmem memory merge --import-bundle`**（内部为 `import_encrypted_bundle_to_agent_checkpoint`）。

默认大模型为本地 **Ollama**（`http://127.0.0.1:11434`）。多模型见 `docs/config.example.toml`，复制为 `~/.mindmemory/config.toml` 后使用 `mmem chat -p fast` 等切换 profile。
