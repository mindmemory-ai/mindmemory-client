# mindmemory-client 与 `mmem` CLI 使用说明

本文描述当前版本的 **Python 库** `mindmemory_client` 与命令行 **`mmem`**（官方示例 CLI）的安装方式、环境变量、子命令及典型流程。架构与设计决策见 [mindmemory-client-设计.md](./mindmemory-client-设计.md)。

**CLI 与 `pnms`：** `mmem` **不**直接 `import pnms`；对话、解密 bundle、合并与落盘一律通过 **`mindmemory_client`**（如 `PnmsMemoryBridge`、`memory_bundle.import_encrypted_bundle_to_agent_checkpoint`）。需安装同工作区 **`pnms`** 包，由库内 `pnms_bridge` 集中加载。

---

## 1. 功能概览

| 能力 | 说明 |
|------|------|
| **记忆引擎（PNMS）** | 本地神经记忆能力；依赖同工作区安装 `pnms`，仅由 `mindmemory_client.pnms_bridge` 等模块引用。 |
| **MindMemory API** | 连接后端 `/api/v1`：`/health`、`/me`、`/agents`、同步签名接口 `begin-submit` / `mark-completed`。 |
| **记忆加密** | 使用 **`K_seed = SHA256(OpenSSH 私钥 PEM)`** 的 32 字节作为 AES-256-GCM 密钥；与 `mindmemory/tools/gen_register_bundle.py` 及设计文档 §11 一致。 |
| **同步产物** | `mmem sync push` 仅提交 **`pnms_bundle.enc`**（PNMS 数据目录打 tar.gz 后再 AES-GCM，Base64 单行写入仓库）。 |
| **多账户** | 本地目录保存多个账户；`mmem account register` / `login` 完成注册与密钥；`resolve_mmem_config()` 自动选用当前账户。 |

推荐使用 **`mmem account`**；脚本/CI 身份请设 **`MMEM_CREDENTIAL_SOURCE=env`** 并同时提供 **`MMEM_USER_UUID`** 与 **`MMEM_PRIVATE_KEY_PATH`**（见 §3.1）。详见 §5.1。

---

## 2. 安装

```bash
# 需先安装同工作区的 PNMS（chat 与 PNMS 依赖）
pip install -e /path/to/pnms

pip install -e /path/to/mindmemory-client
# 开发依赖（pytest 等）
pip install -e ".[dev]"
```

安装后应可执行：

```bash
mmem --help
```

---

## 3. 环境变量与配置文件

### 3.1 身份与环境变量（核心）

**`MMEM_CREDENTIAL_SOURCE`** 决定 `user_uuid` / 私钥从哪里来，避免与多账户 `state.json` 混用产生歧义：

| 值 | 含义 |
|----|------|
| **`account`**（默认） | 身份仅来自 **`~/.mindmemory/state.json`** + **`accounts/<uuid>/`**（`mmem account` 管理）。此时 **忽略** `.env` 里的 `MMEM_USER_UUID` / `MMEM_PRIVATE_KEY_PATH`。 |
| **`env`** | 身份仅来自 **`MMEM_USER_UUID`** + **`MMEM_PRIVATE_KEY_PATH`**（须同时设置，供 CI/脚本）。 |
| **`none`** | 不绑定远端用户；`resolve_mmem_config()` 解析结果无 uuid/私钥（本地 PNMS 等）。 |

**`ClientEnvSettings`**（`pydantic-settings`）**只**声明服务端与身份相关字段：`MMEM_BASE_URL`、`MMEM_PNMS_DATA_ROOT`、`MMEM_TIMEOUT_S`、`MMEM_CREDENTIAL_SOURCE`、`MMEM_USER_UUID`、`MMEM_PRIVATE_KEY_PATH`。其余变量由 **`get_env()`** 直接读（见下表），避免在模型里重复罗列。

| 变量 | 含义 | 默认 |
|------|------|------|
| `MMEM_BASE_URL` | MindMemory 服务根 URL（不含 `/api/v1`） | `http://127.0.0.1:8000` |
| `MMEM_CREDENTIAL_SOURCE` | `account` \| `env` \| `none` | `account` |
| `MMEM_USER_UUID` | 仅当 `env` 时生效 | 无 |
| `MMEM_PRIVATE_KEY_PATH` | 仅当 `env` 时生效 | 无 |
| `MMEM_PNMS_DATA_ROOT` | PNMS 根目录（`from_env`；account 模式下解析后可能被账户逻辑覆盖） | `~/.mindmemory/pnms` |
| `MMEM_TIMEOUT_S` | HTTP 超时（秒） | `60` |
| `MMEM_CONFIG_PATH` | 覆盖 `~/.mindmemory/config.toml` | 内置路径 |
| `MMEM_LLM_PROFILE` / `MMEM_OLLAMA_URL` / `MMEM_OLLAMA_MODEL` / `MMEM_OLLAMA_API_TOKEN` | LLM 覆盖 | 见 `config.toml` |
| `MMEM_CLIENT_CONFIG_DIR` / `MMEM_CLIENT_DATA_DIR` | 客户端主目录（默认均为 **`~/.mindmemory`**；可设 `MMEM_CLIENT_DATA_DIR` 单独把 PNMS 放别处） | `~/.mindmemory` |
| `MMEM_ENV_FILE` | 仅加载该 `.env`（由 `env_loader` 读，须在首次加载前由 shell 设置） | 未设置 |
| `MMEM_SKIP_DOTENV` | `1` 时不读 `.env`（pytest） | 未设置 |
| `MMEM_LOG_LEVEL` | `mmem` 客户端日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `MMEM_LANG` | `mmem chat` 文案语言：`zh` / `en`（与 `LANG` 环境变量互参，未设时优先中文） | 依 `LANG` |
| `MMEM_CHAT_NO_WORKSPACE_PROMPT` | 设为 `1` / `true` 时等价于 **`mmem chat --no-workspace-prompt`**（不读 `mmem-workspace.json` 的 `prompt`） | 未设置 |
| `MMEM_LOG_FILE` | 可选，日志文件路径（额外写入；未设置则仅 stderr） | 未设置 |
| `MMEM_LOG_FORMAT` | 可选，`logging` 格式串（覆盖默认时间+级别+logger+消息） | 内置默认 |
| `MMEM_GIT_SSH_HOST` | Gogs SSH 主机名（`mmem agent init` clone 用） | 未设置 |
| `MMEM_GIT_SSH_PORT` | SSH 端口（非 22 时） | 未设置 |

### 3.2 `.env` 文件

程序通过 **`python-dotenv`** 将 `.env` 合并进 `os.environ`；**已存在于进程环境中的键不会被 `.env` 覆盖**。

- 未设置 `MMEM_ENV_FILE` 时：依次 **`~/.mindmemory/.env`**，再 **`cwd/.env`**（后者覆盖前者同名键）。  
- `MMEM_ENV_FILE`：只加载该文件（实现细节见 `env_loader.py`）。  
- 模板：**`.env.example`**。

首次需要配置时会调用 **`ensure_dotenv_loaded()`**。

### 3.3 LLM 多模型配置（可选）

- **写入配置**：`mmem models configure -p <profile> -t local|remote -M <模型名> [--url ...] [--api-token ...]`，写入 `~/.mindmemory/config.toml`（或 `MMEM_CONFIG_PATH`）。`local` 默认 URL 为本机 `11434`；`remote` 须 `--url`，鉴权用 `--api-token` 或 `--token-stdin`，或环境变量 **`MMEM_OLLAMA_API_TOKEN`**（运行时覆盖文件中的 token）。
- **查看本机/当前 profile 可用模型**：`mmem models tags`（默认用当前解析的 profile；也可 `--url`）。
- **列出 profile**：`mmem models` 或 `mmem models list`。
- 亦可手动复制 [config.example.toml](./config.example.toml)，在 `[[llm.profiles]]` 中填写 `target`、`ollama_base_url`、`ollama_model`、可选 `api_token`；对话时用 `mmem chat -p <name>` 切换。

### 3.4 多账户时的目录约定

- **配置**：`$MMEM_CLIENT_CONFIG_DIR/state.json`（当前账户 UUID）、`accounts/<user_uuid>/account.json`（邮箱等）、`accounts/<user_uuid>/id_ed25519`（私钥）；默认 **`$MMEM_CLIENT_CONFIG_DIR` = `~/.mindmemory`**。  
- **Checkpoint（原 PNMS 数据）**：在 **`mmem account login`** 且已 **`mmem agent init`** 的场景下，推荐路径为 **`$MMEM_CLIENT_DATA_DIR/accounts/<user_uuid>/agents/<agent>/pnms/`**（默认 **`$MMEM_CLIENT_DATA_DIR` = `~/.mindmemory`**）。`MMEM_PNMS_DATA_ROOT` 在配置对象中作为兼容字段存在，解析逻辑见 `resolve_mmem_config`。

若曾使用旧版 `~/.config/mmem/` 或 `~/.cache/mmem/pnms/`，请自行迁移到 `~/.mindmemory/` 下对应结构，或继续用 `MMEM_CLIENT_CONFIG_DIR` / `MMEM_PNMS_DATA_ROOT` 指回旧路径。

---

## 4. 账号与密钥（两种方式）

**方式 A（推荐）**：保持 **`MMEM_CREDENTIAL_SOURCE=account`**（默认），使用 `mmem account register` / `login`：`user_uuid` 与私钥在 **`~/.mindmemory/accounts/`**，由 **`state.json`** 指向当前账户；**勿**在 `.env` 中再写 uuid/私钥。

**方式 B（脚本/CI）**：显式 **`MMEM_CREDENTIAL_SOURCE=env`**，并同时设置：

```bash
export MMEM_CREDENTIAL_SOURCE=env
export MMEM_BASE_URL=https://your-mmem-host
export MMEM_USER_UUID=<uuid>
export MMEM_PRIVATE_KEY_PATH=/path/to/private_key
```

> **sync API 签名**使用 **Ed25519**（`load_ed25519_private_key`）；`mmem account register` 生成的密钥与此一致。

---

## 5. CLI 命令总览

```text
mmem
├── doctor              # 环境检查（含记忆引擎是否可被库加载）
├── models              # 列出 LLM profile
├── chat                # 对话（ChatMemorySession / PnmsMemoryBridge）
├── agent               # Agent 工作区：checkpoint 目录 + 记忆 Git 仓库（clone）
│   ├── init            # 服务端注册 Agent/仓、本地目录、git clone
│   └── info            # 工作区 / pnms / repo 路径
├── pnms                # 查看 checkpoint 目录（概念 meta、graph.db；读盘，不 import pnms）
│   ├── status          # 目录 / meta / 边数摘要
│   ├── concepts        # meta.json 与各 .pt
│   └── graph           # graph.db 边（按权降序）
├── account             # 多账户：注册、登录、登出、切换、whoami
├── sync
│   ├── encrypt-file    # 任意文件 → K_seed AES-GCM → Base64
│   ├── decrypt-file    # 逆操作
│   ├── push            # 打包 checkpoint → pnms_bundle.enc → git + MMEM sync
│   └── ping            # GET /me、/agents
└── memory
    ├── merge           # git fetch + pull --rebase；可选 --import-bundle
    └── import-bundle   # 解密 pnms_bundle.enc → memory_bundle 合并并落盘
```

查看帮助：

```bash
mmem --help
mmem account --help
mmem sync --help
mmem memory --help
mmem pnms --help
mmem agent --help
```

---

## 5.1 `mmem account`（多账户）

| 子命令 | 说明 |
|--------|------|
| `register` | 交互输入邮箱、账户密码、私钥备份口令；生成密钥对，调用服务端注册与 `setup-key`，保存 `user_uuid` 与私钥，设为当前账户。 |
| `login` | 邮箱 + 账户密码。若本机已有该 `user_uuid` 目录下的私钥，则不再要求备份口令；否则从 `GET /me/encrypted-private-key-backup` 拉取备份并用备份口令解密、写入本地。 |
| `logout` | 清除 `state.json` 中的当前账户指针（**不删除**本地账户目录与私钥）。 |
| `list` | 列出本机已保存的账户（邮箱、`user_uuid`）；当前账户标 `*`。 |
| `use <邮箱或完整 user_uuid>` | 切换到已存在于本机的账户（需本地已有私钥文件）。 |
| `whoami` | 打印 `resolve_mmem_config` 解析结果，并在有 `user_uuid` 时请求 **`GET /me`**。 |

---

## 6. `mmem doctor`

检查：Python 版本、**`mindmemory_client.pnms_bridge.is_memory_engine_available()`**（即 `pnms` 是否可被库加载）、MindMemory `/health`（失败仅警告）、**客户端配置目录**与 **state 当前账户**、解析后的 **`user_uuid` / 私钥路径**、当前 LLM profile、**Ollama `/api/tags`**。  
`doctor` / `chat` / `sync` / `ping` 使用 **`resolve_mmem_config()`**（见 **`MMEM_CREDENTIAL_SOURCE`**，§3.1、§3.4）。  
可选：`--base-url`、`--config`。

---

## 7. `mmem models`

列出 `config.toml` 中的 profile 及解析后的默认 profile；用于确认 Ollama 地址与模型名。

---

## 8. `mmem agent`（工作区与记忆仓库）

远端 **Gogs 仓库** 在 MindMemory **首次 `begin-submit`** 时由服务端创建（见服务端 `sync` 路由）。CLI 侧推荐顺序：

1. 配置 **`MMEM_GIT_SSH_HOST`**（及可选 **`MMEM_GIT_SSH_PORT`**），与 Gogs SSH 一致。
2. **`mmem agent init <名称>`**：向服务端请求注册（`begin-submit` + 失败型 `mark_completed` 释放锁）、在 `accounts/<user_uuid>/agents/<名称>/` 写入 `agent.json`、创建 **`pnms/`** 与将记忆仓库 **`git clone`** 到 **`repo/`**（使用账户私钥 `GIT_SSH_COMMAND`）。
3. **`mmem chat --agent <名称>`**、**`mmem sync push --agent <名称>`** 会自动使用该工作区下的 **`pnms/`** 与 **`repo/`**（无需再手写 `--git-dir`，仍可显式覆盖）。

**扩展**：与 **`pnms/`**、**`repo/`** 同级有 **`workspace/`**（源文件池）；通过 **`workspace/mmem-workspace.json`**（**`schema_version: 2`**，含 **`sync`** 与可选 **`prompt`**，不进入记忆 Git）声明打进 **`mmem/bundles/extras.enc`** 的路径及（可选）LLM 上下文文件。记忆仓 **`repo/.gitignore`** 建议见该文档 **§5.1**。全文：**[memory-repo-extended-layout.md](./memory-repo-extended-layout.md)**。

OpenClaw 等环境应将**当前选中的 Agent 名**传入同一套客户端 API（与 `agent_name` 一致）。

---

## 9. `mmem chat`

与本地 **Ollama**（默认）或 `mock` / `echo` 对话，每轮通过 **PNMS** 更新记忆并 `save_checkpoint`。Ollama 侧优先调用 **`POST /api/chat`**；若返回 **404**（例如版本过旧无 Chat API），会自动回退 **`POST /api/generate`**。若 **两个接口都返回 404**，多为 **模型名与 `ollama list` 不一致** 或 **`MMEM_OLLAMA_URL` 未指向正在运行的 Ollama**（Ollama 0.18+ 均提供上述 API）。请保证已 **`ollama pull`** 且模型名与 profile 完全一致。

| 选项 | 说明 |
|------|------|
| `-m` / `--message` | 单次提问后退出 |
| `--agent` | Agent 名（PNMS 与 MMEM 隔离；默认 `BT-7274`） |
| `--llm` | `ollama`（默认）、`mock`、`echo` |
| `-p` / `--profile` | LLM profile 名 |
| `--ollama-url` / `--model` | 覆盖当前 profile |
| `--no-remote` | 不请求 MindMemory `/health` |
| `--config` | `config.toml` 路径 |
| `--no-workspace-prompt` | 不读取 **`workspace/mmem-workspace.json`** 的 **`prompt`** 段（仅 PNMS 默认系统提示）；也可用 **`MMEM_CHAT_NO_WORKSPACE_PROMPT=1`** |
| `--quiet` / `-q` | 不打印工作区状态行（启动时仍会做日志） |

**需先** `mmem account login`（或配置 `MMEM_CREDENTIAL_SOURCE=env` 与私钥）；未登录无法使用对话。PNMS 目录为 `accounts/<user_uuid>/agents/<agent>/pnms`。

### 9.1 工作区提示与语言

- **默认 Agent `BT-7274`**：首次在 `workspace/` 下无 **`mmem-workspace.json`** 时，会从包内模板复制 **`identity.md`**、**`soul.md`** 与配置（见 **`mindmemory_client.agent.BT-7274.workspace`**）。
- **其他 Agent 名**：无内置模板时，请自行在 **`workspace/mmem-workspace.json`** 中配置 **`sync`** / **`prompt`**，或从 **`agent/BT-7274/workspace/`**（仓库根镜像，与包内一致）复制后改文件名与 `include`。
- **Ollama**：工作区 **`prompt`** 正文作为 **`/api/chat`** 的 **system** 消息（与 PNMS 检索出的 **user** 消息分离）；`mock` / `echo` 则将工作区正文前缀到 PNMS 上下文字符串前，便于离线对照。
- **文案语言**：**`MMEM_LANG=zh|en`**，或 **`LANG`** 以 `zh` / `en` 开头时推断；影响 **启动状态行**、**默认系统提示**、**Ollama 包装句**。
- **仓库镜像校验**：在仓库根执行 **`python tools/check_agent_workspace_mirror.py`**，确认 **`src/mindmemory_client/agent/BT-7274/workspace/`** 与 **`agent/BT-7274/workspace/`** 文件一致（CI 可复用）。

### 9.2 `mmem pnms`（概念图与记忆图）

查看当前 **user + agent** 对应 checkpoint 目录下**已落盘**的内容：**概念模块**（`meta.json`、各 `*.pt`）与**记忆图**（SQLite `graph.db`）。子命令：`status`（摘要）、`concepts`（meta 与文件列表）、`graph`（按边权列出前 N 条边，`--limit`）。共用 `--agent`、`--user`（覆盖 `user_uuid`）、`--json`。

说明：每轮 `mmem chat` 结束时会 `save_checkpoint`，在 checkpoint 目录写入 **概念**（`meta.json` / `*.pt`）、**图**（`graph.db`）、**记忆槽**（`memory_slots.json`）与**个人状态**（`memory_session.pt`，含 S_t 与轮次）；下次启动会从同目录恢复。

---

## 10. `mmem sync`

### 10.1 `mmem sync encrypt-file` / `decrypt-file`

对任意文件使用 **`K_seed`** 做 AES-256-GCM（格式：`nonce(12)‖密文‖tag`，再 Base64 单行）。

- 需 **`--private-key <path>`**（或确保环境变量可被 Typer 读取；若命令行未传参，请以环境变量配合文档中的路径说明使用）。  
- `encrypt-file`：`-o` 输出文件；否则打印到 stdout。  
- `decrypt-file`：`-o` 输出明文文件；否则二进制写到 stdout。

### 10.2 `mmem sync push`

将 **PNMS 数据目录**（`tar.gz` 后）用 **`K_seed`** 加密，得到 **`pnms_bundle.enc`** 提交到 Git 并调用 MindMemory 同步接口。

**必须**：已解析的 **`private_key_path`**（`env` 模式或 `account` 模式下的 `id_ed25519`）。  
**需要完整同步时还需**：**`user_uuid`**；默认会校验 **`origin` URL** 是否包含 Gogs 用户名片段（`user_uuid` 去横线）；可用 **`--skip-remote-check`** 跳过。

| 选项 | 说明 |
|------|------|
| `--agent` | Agent 名（必填） |
| `--schema` | 与 `memory_schema_version` 一致，即 `git push` 的目标分支名；**默认**与 PNMS `get_memory_format_version()` 相同（如 `1.0.0`） |
| `--git-dir` | 已配置 **`origin`** 的本地记忆仓库；省略时若已 **`mmem agent init`** 则使用 `.../agents/<agent>/repo/` |
| `--pack-pnms` | 指定 PNMS 目录；不指定时使用 **`mmem agent init`** 后的 `.../agents/<agent>/pnms/` 或 `MMEM_PNMS_DATA_ROOT/<user>/<agent>/` |
| `--skip-remote-check` | 不校验 `origin` URL |
| `--sync-extras` | 若存在 **`workspace/mmem-workspace.json`**，按 **`sync.bundles`** 将文件打包为 **`mmem/bundles/extras.enc`**（与 `pnms_bundle.enc` 同一 `K_seed`），并与 PNMS bundle **同一次 commit** 推送（需已解析到记忆仓库；无仓库时跳过并提示） |

**流程（已解析到记忆仓库目录）**：

1. `git fetch origin`  
2. 比较本地 `HEAD` 与 `origin/<schema>`：若为 **behind** 或 **diverged**，**不占用同步锁**，退出码 **2**，并提示先执行 **`mmem memory merge`**  
3. 否则：`begin-submit` → 写入 `pnms_bundle.enc` →（可选 `--sync-extras`）写入 `mmem/bundles/extras.enc` → `git add/commit/push origin HEAD:refs/heads/<schema>` → `mark-completed`

**无记忆仓库路径**（未 `--git-dir` 且未 `agent init`）：仅生成当前目录 `pnms_bundle.enc`，不占锁。

### 10.2.1 `mmem sync extras-dry-run`

根据 **`workspace/mmem-workspace.json`**（或 **`--manifest`** 指向该文件）解析 **`sync.bundles`**，**仅打印**将打入 extras **tar** 的相对路径（**不**加密、**不**写 `repo/`）。需已登录。**`--json`** 输出 `arcnames` 与 `warnings`。

### 10.3 `mmem sync ping`

需已解析的 **`user_uuid`**，调用 **`GET /api/v1/me`** 与 **`GET /api/v1/agents`**（Header `X-User-UUID`），用于验证账号与 Agent 列表。

---

## 11. `mmem memory merge` / `mmem memory import-bundle`

### 11.1 `mmem memory merge`

在**已配置 `origin`** 的记忆仓库中执行：

- `git fetch origin`
- `git pull --rebase origin <schema>`（`--schema` 默认与 `resolve_memory_schema_version(None)` 一致）

**`--dry-run`** 只打印将执行的命令。

**`--import-bundle`**：在上述 Git 步骤**成功**后，对 `<git-dir>/pnms_bundle.enc` 调用与 **`mmem memory import-bundle`** 相同的库流程（见 §11.2）。需要已配置私钥（`K_seed`）。

**`--import-extras`**：在上述 Git 步骤**成功**后，若存在 `<git-dir>/mmem/bundles/extras.enc`，则解密并解压到当前 Agent 的 **`workspace/`**（见 [memory-repo-extended-layout.md](./memory-repo-extended-layout.md)）。可与 `--import-bundle` 同时使用。

### 11.2 `mmem memory import-bundle`

不操作 Git，仅处理加密 bundle：

1. 用 **`K_seed`** 解密 **`pnms_bundle.enc`** 为 tar.gz，解压到**系统临时目录**。
2. 构造 **`PnmsMemoryBridge`**（checkpoint 为当前账户下 `accounts/<user_uuid>/agents/<agent>/pnms`）。
3. 调用 **`merge_external_checkpoint`**（底层为已安装 `pnms` 的 `merge_memories`，语义以 `pnms` 文档为准）。
4. **`persist_checkpoint`** 将当前内存态写入上述 `pnms/`。

失败时库抛出 **`MemoryEngineError`**（CLI 会格式化为可读说明）。API 入口：**`mindmemory_client.memory_bundle.import_encrypted_bundle_to_agent_checkpoint`**；**`format_memory_engine_error`** 用于展示。

**`--bundle`**：显式指定密文路径时可省略 **`--git-dir`**；否则默认 **`<git-dir>/pnms_bundle.enc`**（`git-dir` 可由 Agent 工作区自动解析）。

**`--import-extras`**：在 PNMS 导入之后（或配合 **`--extras-only`** 单独使用），从 **`<git-dir>/mmem/bundles/extras.enc`** 解密并解压到 **`workspace/`**。**`--extras-only`**：不合并 **`pnms_bundle.enc`**，仅解压 extras（需 **`--git-dir`** 或已初始化的 Agent 记忆仓库）。

---

## 12. Python 库（简要）

```python
from mindmemory_client import (
    MmemApiClient,
    PnmsMemoryBridge,
    ChatMemorySession,
    ChatTurnResult,
    MemoryEngineError,
    import_encrypted_bundle_to_agent_checkpoint,
    format_memory_engine_error,
    is_memory_engine_available,
    resolve_mmem_config,
    encrypt_memory_base64,
    decrypt_memory_base64,
)

cfg = resolve_mmem_config()
with MmemApiClient(cfg) as api:
    api.health()
```

更多模块：`memory_bundle`、`pnms_bridge`、`register_crypto`、`memory_crypto`、`sync`（payload 签名）、`api` 等，见源码包 `src/mindmemory_client/`。集成方应通过上述公开 API 使用记忆能力，**避免**在插件/业务代码中直接 `import pnms`（除非维护 `pnms` 本身）。

---

## 13. 相关文档

| 文档 | 内容 |
|------|------|
| [mindmemory-client-设计.md](./mindmemory-client-设计.md) | 架构、密钥、CLI 设计 |
| [memory-repo-extended-layout.md](./memory-repo-extended-layout.md) | **`workspace`**、清单、**`extras.enc`**、**`repo/.gitignore` 建议（§5.1）** |
| [config.example.toml](./config.example.toml) | LLM profile 示例 |
| `mindmemory/docs/mmem-web-api.md` | 后端 REST 约定 |
| `mindmemory/tools/gen_register_bundle.py` | 注册用密钥与指纹辅助 |
