# mindmemory-client

Python 库与官方示例 CLI **`mmem`**：长期记忆（由 `pnms` 提供实现，**仅**在库内 `pnms_bridge` 等模块引用）+ MindMemory `/api/v1`（含 sync 签名）。**CLI 与业务集成应通过 `mindmemory_client` 公开 API，不要直接 `import pnms`。**

开发安装需先安装同工作区的 `pnms`：

```bash
pip install -e ../pnms
pip install -e ".[dev]"
```

设计见 `docs/mindmemory-client-设计.md`；安装与 CLI 用法见 `docs/mmem-使用说明.md`。环境变量可通过 **`~/.mindmemory/.env`** 或 **`cwd/.env`** 配置（模板见 `.env.example`）。多账户场景保持 **`MMEM_CREDENTIAL_SOURCE=account`**（默认），勿在 `.env` 写死 `MMEM_USER_UUID`/`MMEM_PRIVATE_KEY_PATH`；脚本身份用 **`MMEM_CREDENTIAL_SOURCE=env`**。

**同步**：`mmem sync push` 向 Git 提交加密后的 **`pnms_bundle.enc`**（本地 checkpoint 目录打包）。推送前会 `git fetch` 并与远端比较；若远端较新或分叉，请先 **`mmem memory merge`**。需要把远端 bundle 合入本地时，使用 **`mmem memory import-bundle`** 或 **`mmem memory merge --import-bundle`**（内部为 `import_encrypted_bundle_to_agent_checkpoint`）。

默认大模型为本地 **Ollama**（`http://127.0.0.1:11434`）。多模型见 `docs/config.example.toml`，复制为 `~/.mindmemory/config.toml` 后使用 `mmem chat -p fast` 等切换 profile。
