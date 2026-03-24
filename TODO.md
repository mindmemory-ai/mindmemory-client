# mindmemory-client 开发清单

依据 [docs/mindmemory-client-设计.md](docs/mindmemory-client-设计.md)。完成一项则勾选并提交 git。

**摘要**：库与 **`mmem`** CLI 已覆盖 PNMS、MMEM API、**`workspace/` + extras 密文**（**`mmem-workspace.json`**、打包、解密、`sync push --sync-extras`、`memory` 侧 `--import-extras`、**`sync extras-dry-run`**）；**`mmem chat`** 已读取 **`prompt`** 并内置 **BT-7274** 工作区模板；**大型集成**见 **`tests/test_large_memory_scenario.py`**。**待完善项**见 **「客户端后续改进」**、文末「宿主集成」，设计见 [mindmemory-client-设计.md §10.8](docs/mindmemory-client-设计.md)。

## 依赖安装（开发）

```bash
cd ../pnms && pip install -e .
cd ../mindmemory-client && pip install -e ".[dev]"
```

## 库 `mindmemory_client`

- [x] `pyproject.toml` + `src` 布局、可编辑安装
- [x] `config`：`MindMemoryClientConfig`（base_url、user_uuid、private_key_path、pnms_data_root、timeout）
- [x] `sync`：`build_begin_submit_payload` / `build_mark_completed_payload` / `sign_payload`（与 `mindmemory/tests/test_integration_flow.py` 字段一致）
- [x] `api`：`MmemApiClient` — `health`、`get_me`、`list_agents`、`begin_submit`、`mark_completed`
- [x] `pnms_bridge`：`PnmsMemoryBridge` — 按 `user_uuid` + `agent_name` 设置 `concept_checkpoint_dir` 与 `user_id`
- [x] `session`：`ChatMemorySession` — `handle_turn`（PNMS `handle` + `content_to_remember` 默认规则）
- [x] 单元测试：`tests/test_sync_payload.py`、`tests/test_llm_profiles.py`、`tests/test_register_crypto.py`、`tests/test_memory_crypto.py`；**`tests/test_sync_manifest.py`**、**`tests/test_workspace_extras.py`**
- [x] `llm_profiles` + `ollama_llm`：默认 Ollama；`~/.mindmemory/config.toml` 多 profile；环境变量覆盖

### 加密与注册材料（见设计文档 §11、`mindmemory/tools/gen_register_bundle.py`）

- [x] `register_crypto`：`key_fingerprint_from_public_key_ssh`、`k_seed_bytes_from_private_key_openssh`、`encrypted_password_hex_from_private_key_openssh`
- [x] `keys.read_openssh_private_key_pem`
- [x] `memory_crypto`：AES-256-GCM，`K_seed` 32 字节；`encrypt_memory_base64` / `decrypt_memory_base64`
- [x] 记忆载荷：`nonce(12)‖ciphertext‖tag` → Base64

## CLI `mmem`

- [x] `mmem doctor` — 依赖、MindMemory、Ollama（`/api/tags`）
- [x] `mmem chat` — 默认 `--llm ollama`；`--profile` / `-p`；`--ollama-url`、`--model`；`mock`/`echo`；`--no-remote`；**`--no-workspace-prompt`** / **`MMEM_CHAT_NO_WORKSPACE_PROMPT`**；**`-q`**；**`prompt`** → Ollama **system**（见 **`chat_strings`**、**`ollama_llm.build_ollama_llm`**）
- [x] `mmem models` — 列出已加载 profile
- [x] **`mmem sync encrypt-file` / `decrypt-file`** — K_seed 加解密文件
- [x] **`mmem sync push`** — **`pnms_bundle.enc`**（PNMS tar.gz + K_seed）；可选 **`--sync-extras`** 生成 **`mmem/bundles/extras.enc`**；无 `--git-dir` 时只写本地 **`./pnms_bundle.enc`**
- [x] **推送前**：`git fetch` + 与 `origin/<schema>` 比较；**behind/diverged** 时**不占锁**并退出（exit 2），提示先 **`mmem memory merge`**
- [x] **`mmem memory merge`** — `git fetch` + `git pull --rebase`；可选 **`--import-bundle`** / **`--import-extras`**
- [x] **`mmem memory import-bundle`** — `memory_bundle` 解密合并落盘；CLI 不直接 import pnms
- [x] **origin 校验**：默认要求 URL 含 Gogs 用户名片段（`--skip-remote-check` 可关）
- [x] **`--pack-pnms`**：覆盖默认 PNMS 目录（默认 `MMEM_PNMS_DATA_ROOT/<user>/<agent>/`）

## 联调（需本机环境，不自动 CI）

- [x] 对真实 `MMEM_BASE_URL`：手动运行 `mmem doctor` + `mmem chat -m "hi" --llm mock`（`--no-remote` 已可离线验证 PNMS）
- [x] `MMEM_INTEGRATION=1`（mindmemory 仓库）全链路：需 MySQL、Gogs、已注册账号与私钥；示例：`cd ../mindmemory && MMEM_INTEGRATION=1 MMEM_BASE_URL=http://127.0.0.1:8000 GOGS_REPO_ROOT=…/mindmemory/.data/gogs-repositories python -m pytest tests/test_integration_flow.py -v`
- [x] 本仓库自动化：**`tests/test_integration_git_smoke.py`**（临时 git + extras 往返，无需远端）
- [x] **`tests/test_large_memory_scenario.py`**：30 轮 + bundle 合并 + 20 轮、提示词落盘（**`@pytest.mark.integration`**）

---

## 客户端后续改进（设计见 [docs/mindmemory-client-设计.md §10.8](docs/mindmemory-client-设计.md)）

- [x] **可操作错误提示**：同步 / Git 落后 / 签名校验失败等，在提示中附带建议命令（如先 **`mmem memory merge`**）
- [x] **调试可观测性**：**`mmem chat`** 可选 **`--verbose`** / **`MMEM_CHAT_DEBUG`**，打印 **`num_slots_used`**、**`phase`**、**`context` 长度**
- [x] **CLI 回归**：**Typer `CliRunner`** 覆盖 **`mmem`** 关键子命令退出码与关键输出片段（**`tests/test_cli_mmem.py`**）
- [x] **远端 opt-in E2E**：**`pytest -m e2e_remote`** + **`MMEM_BASE_URL`** 门控（**`tests/test_e2e_remote_mmem.py`**）
- [x] **OpenAI 兼容 LLM**：profile **`openai_chat`** + **`mmem chat --llm openai`**（**`OPENAI_API_KEY`** / **`OPENAI_BASE_URL`**）
- [x] **（可选）extras 进对话**：**`read_extras_enc_text_block`** / **`merge_workspace_prompt_and_extras`**；**`mmem chat --chat-extras`** / **`MMEM_CHAT_INCLUDE_EXTRAS`**
- [x] **发布**：**0.2.0** + **`CHANGELOG.md`**；**README** 区分最小安装与 **`pnms`/`torch`** 完整能力
- [x] **i18n 统一**：文档固定 **`mmem chat` 多语言**；**`doctor` 等暂固定中文**（见 **`docs/mmem-使用说明.md`** §9.1）

---

## workspace + `mmem-workspace.json`（见 [docs/memory-repo-extended-layout.md](docs/memory-repo-extended-layout.md)）

**已实现**：**`pnms/`**、**`repo/`**、**`workspace/`** 同级；**`workspace/mmem-workspace.json`**（**仅** `schema_version: 2`，不入记忆 Git）声明 **`sync.bundles`** → **`mmem/bundles/extras.enc`**，可选 **`prompt`**；与 **`K_seed`**、**`mmem sync push`** / **`mmem memory merge`** 同一套同步流程。

### 目录与初始化

- [x] `agent_workspace`：提供 **`resolve_workspace_dir_for_user_agent`** 指向 `<agent>/workspace/`，与 `pnms`、`repo` 同级
- [x] **`write_agent_config`** / **`ensure_default_agent_workspace`**：创建 **`workspace/`**；若尚无 **`mmem-workspace.json`** 且存在包内模板则 **播种**（当前 **BT-7274**）
- [x] 文档：**`repo/.gitignore` 建议片段**见 [memory-repo-extended-layout.md §5.1](./docs/memory-repo-extended-layout.md)；`mmem-使用说明.md` 已补充 sync / merge / import-bundle 行为

### 配置 `mmem-workspace.json`

- [x] **`WorkspaceConfig`**（**`sync`** + 可选 **`prompt`**）、**`load_workspace_config`**，见 **`mindmemory_client/sync_manifest.py`**；仅 **`schema_version: 2`**
- [x] 解析与校验失败时抛出 **`SyncManifestError`**
- [x] **路径安全**：`sync.bundles[].include` 禁止 **`..`**、绝对路径；tar 解压时校验成员路径
- [x] **`optional`**：未匹配文件时记 warning 或跳过（非 optional 则报错）
- [x] **`prompt_context_paths_for_workspace`**：供宿主拼装 LLM 上下文（不参与加密，除非路径也在 `sync` 中）
- [x] **`read_workspace_prompt_block`**（**`workspace_prompt.py`**）：CLI **`mmem chat`** 拼系统提示
- [x] **`seed_default_workspace_template`**：包内 **`mindmemory_client/agent/BT-7274/workspace/`** 播种；仓库根 **`agent/BT-7274/workspace/`** 为可选镜像

### 库 API（mindmemory_client）

- [x] **`pack_workspace_extras_to_enc`** / **`pack_workspace_extras_from_manifest_file`**：tar.gz → **`encrypt_memory_base64`**
- [x] **`decrypt_extras_bundle_file_to_workspace`** / **`decrypt_extras_bundle_bytes_to_workspace`**：解密 → 解压到 `workspace/`；**默认跳过** **`mmem-workspace.json`**
- [x] 与 **`memory_bundle`** 边界：extras **仅**落 **`workspace/`**，不经 PNMS **`merge_memories`**

### `repo/` 内产物路径（与 §5 兼容）

- [x] 固定：**`mmem/bundles/extras.enc`**（相对记忆 Git 根）

### CLI `mmem`

- [x] **`mmem sync push --sync-extras`**：**`mmem-workspace.json`** 存在则生成 **`mmem/bundles/extras.enc`** 并与 **`pnms_bundle.enc`** 同批 **`git add` / commit**
- [x] **`mmem memory merge --import-extras`**；**`mmem memory import-bundle --import-extras`** / **`--extras-only`**
- [x] （可选）干跑：**`mmem sync extras-dry-run`**（**`--json`**）仅列出将打入 extras tar 的相对路径

### 测试与安全

- [x] 单元测试：`tests/test_sync_manifest.py`、`tests/test_workspace_extras.py`、**`tests/test_workspace_prompt.py`**
- [x] 集成测试（可选）：**`tests/test_integration_git_smoke.py`**（临时 `git init` + `mmem/bundles/extras.enc` commit + 解密回写）

### CLI / workspace 演进（设计见 `docs/mindmemory-client-设计.md` §10.5.1、`memory-repo-extended-layout.md` §3.2a）

- [x] **`mmem chat --no-workspace-prompt`**（或 **`MMEM_CHAT_NO_WORKSPACE_PROMPT=1`**）：跳过 **`read_workspace_prompt_block`**
- [x] **启动可观测性**：终端状态行（`--quiet` 关闭）；解析失败等写入 **`warnings`** 并 **`typer.echo(..., err=True)`**
- [x] **Ollama**：**`system`** + **`user`**（`build_ollama_llm`）；**`session_system_default`** 仅短句，工作区人格不重复塞进 PNMS `system_prompt`
- [x] **文案 i18n**：**`mindmemory_client/chat_strings.py`**（**`MMEM_LANG`** / **`LANG`**，`zh`/`en`）
- [x] **模板镜像**：**`tools/check_agent_workspace_mirror.py`** + **`tests/test_workspace_prompt.py`** 中调用
- [x] **文档**：**`docs/mmem-使用说明.md`** §9.1（非 BT-7274、镜像校验、语言）

### 宿主集成（本仓库不实现，供 OpenClaw / 自研插件跟踪）

- [ ] **Claw 记忆插件**：实例启动时维护 **`mmem-workspace.json`** → 调用 **mindmemory-client** 打包/加密 → **`mmem sync push`**（或等价流程）；**不在**本库内绑定 Claw。
- [ ] （可选）**LLM 上下文**：宿主侧按 [memory-repo-extended-layout.md §6](docs/memory-repo-extended-layout.md) 将 **workspace `prompt` / extras 解密内容** 与 PNMS **`get_context`** 拼接；**`mmem chat`** 已实现 **`prompt`** 路径，**extras 解密正文**仍可由宿主按需叠加。
