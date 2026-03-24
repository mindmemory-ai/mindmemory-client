# mindmemory-client

**MindMemory 官方 Python 客户端库**与示例命令行 **`mmem`**：在**不直接依赖业务代码 `import pnms`** 的前提下，提供神经记忆引擎（**PNMS**）桥接、MindMemory **HTTP `/api/v1`**（健康检查、账户、Agent、**同步签名** `begin-submit` / `mark-completed`）、记忆 **AES-GCM** 加解密、**workspace** 与 **`extras.enc`** 同步等能力。

---

## 许可证（重要）

本仓库采用 **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)**（**`LICENSE`** 全文）。

- **允许**：在非商业前提下使用、修改、再分发；个人学习、研究、公益/教育/公共机构等场景见许可证正文。  
- **不允许**：**商业使用**（以营利为目的或面向商业客户的提供产品/服务/SaaS 等，以许可证条文为准）。  
- **商业授权**：若需在商业环境使用，请与版权方另行取得书面许可。

> 全文法律条款以根目录 **`LICENSE`** 为准；**`Required Notice:`** 见该文件。

---

## 文档索引（`docs/`）

| 文档 | 内容 |
|------|------|
| [**mmem-使用说明.md**](docs/mmem-使用说明.md) | **主手册**：环境变量、`mmem` **全部子命令**、`mindmemory_client` **库 API 参考**（配置、HTTP、PNMS、workspace、LLM 等）。 |
| [**mindmemory-client-设计.md**](docs/mindmemory-client-设计.md) | 架构、密钥与加密、CLI 设计、与 MindMemory / PNMS 的边界。 |
| [**memory-repo-extended-layout.md**](docs/memory-repo-extended-layout.md) | **`workspace/`**、**`mmem-workspace.json`**、**`extras.enc`**、记忆仓 **`repo/`** 布局与 LLM 上下文顺序（§6）。 |
| [**config.example.toml**](docs/config.example.toml) | LLM 多 profile 示例（Ollama / OpenAI 兼容），可复制为 `~/.mindmemory/config.toml`。 |

其他：**[`CHANGELOG.md`](CHANGELOG.md)**（版本记录）、**[`.env.example`](.env.example)**（环境变量模板）、**[`TODO.md`](TODO.md)**（开发清单）。

上游 MindMemory 服务端文档若位于同工作区的 `mindmemory` 仓库，可参考其中的 API / Web 说明（路径以该仓库为准）。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| **PNMS（神经记忆）** | 经 **`mindmemory_client.pnms_bridge`** 加载同工作区 **`pnms`** 包；**`mmem chat`**、checkpoint 合并等走此路径。 |
| **MindMemory API** | **`MmemApiClient`**：`/health`、`/me`、`/agents`、同步相关接口（Ed25519 签名）。 |
| **加密与同步** | **`K_seed`**（私钥派生）与 **`pnms_bundle.enc`** / **`extras.enc`** 一致；**`mmem sync push`**、**`memory merge`** / **`import-bundle`**。 |
| **Workspace** | **`read_workspace_prompt_block`**、**`read_extras_enc_text_block`**、清单 **`load_workspace_config`** 等（详见使用说明 §12）。 |

---

## 安装层次

| 范围 | 命令 | 能力 |
|------|------|------|
| **最小** | `pip install -e .`（或发布后自 PyPI 安装） | 配置、HTTP、签名、workspace/extras **库 API** 等；**不含**可运行的神经记忆引擎。 |
| **完整（推荐开发）** | 先安装 **`pnms`** 再安装本仓库 **`".[dev]"`** | **`mmem chat`**、**`mmem doctor`** 中的引擎检测、集成测试；依赖 **PyTorch** 等，体积较大。 |

```bash
# 完整能力（与仓库 TODO 一致）
pip install -e ../pnms
pip install -e ".[dev]"
```

安装后应能运行：

```bash
mmem --help
```

---

## 快速开始（CLI）

1. **配置环境**：复制 **`.env.example`** 为 **`~/.mindmemory/.env`** 或项目 **`cwd/.env`**`，设置 **`MMEM_BASE_URL`** 等（多账户勿在 `.env` 写死 `MMEM_USER_UUID`，见使用说明 §3）。  
2. **登录**：`mmem account register` / `mmem account login`。  
3. **Agent 与仓库**：`mmem agent init <名称>`（PNMS 目录 + 记忆 Git **`repo/`**）。  
4. **对话**：`mmem chat`（默认 Ollama；可选 **`--llm openai`**、**`--chat-extras`** 等）。  
5. **同步**：`mmem sync push --agent <名称>`（含 **`pnms_bundle.enc`**；可选 **`--sync-extras`**）。

详细选项与库用法见 **[docs/mmem-使用说明.md](docs/mmem-使用说明.md)**。

---

## 包布局（源码）

```text
src/
  mindmemory_client/   # 库：api、pnms_bridge、session、memory_bundle、workspace_*、llm_profiles 等
  mmem_cli/              # Typer：`mmem` 入口 main.py
```

集成时请 **`from mindmemory_client import ...`** 使用公开符号（见 **`__init__.py`**），**不要**在业务代码中直接 **`import pnms`**（除非维护 PNMS 本身）。

---

## 版本与标签

当前版本见 **`pyproject.toml`** 的 **`version`** 与 **[`CHANGELOG.md`](CHANGELOG.md)**；发布标签形如 **`v0.2.0`**。

---

## 相关链接

- PolyForm Noncommercial：**<https://polyformproject.org/licenses/noncommercial/1.0.0/>**
