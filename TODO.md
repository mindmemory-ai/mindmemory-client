# mindmemory-client 开发清单

依据 [docs/mindmemory-client-设计.md](docs/mindmemory-client-设计.md)。完成一项则勾选并提交 git。

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
- [x] 单元测试：`tests/test_sync_payload.py`、`tests/test_llm_profiles.py`、`tests/test_register_crypto.py`、`tests/test_memory_crypto.py`
- [x] `llm_profiles` + `ollama_llm`：默认 Ollama；`~/.mindmemory/config.toml` 多 profile；环境变量覆盖

### 加密与注册材料（见设计文档 §11、`mindmemory/tools/gen_register_bundle.py`）

- [x] `register_crypto`：`key_fingerprint_from_public_key_ssh`、`k_seed_bytes_from_private_key_openssh`、`encrypted_password_hex_from_private_key_openssh`
- [x] `keys.read_openssh_private_key_pem`
- [x] `memory_crypto`：AES-256-GCM，`K_seed` 32 字节；`encrypt_memory_base64` / `decrypt_memory_base64`
- [x] 记忆载荷：`nonce(12)‖ciphertext‖tag` → Base64

## CLI `mmem`

- [x] `mmem doctor` — 依赖、MindMemory、Ollama（`/api/tags`）
- [x] `mmem chat` — 默认 `--llm ollama`；`--profile` / `-p`；`--ollama-url`、`--model`；`mock`/`echo`；`--no-remote`
- [x] `mmem models` — 列出已加载 profile
- [x] **`mmem sync encrypt-file` / `decrypt-file`** — K_seed 加解密文件
- [x] **`mmem sync push`** — 仅 **`pnms_bundle.enc`**（PNMS 目录 tar.gz + K_seed AES-GCM）；无 `--git-dir` 时只写本地 `./pnms_bundle.enc`
- [x] **推送前**：`git fetch` + 与 `origin/<schema>` 比较；**behind/diverged** 时**不占锁**并退出（exit 2），提示先 **`mmem memory merge`**
- [x] **`mmem memory merge`** — `git fetch` + `git pull --rebase`；可选 `--import-bundle` → `import_encrypted_bundle_to_agent_checkpoint`
- [x] **`mmem memory import-bundle`** — `memory_bundle` 解密合并落盘；CLI 不直接 import pnms
- [x] **origin 校验**：默认要求 URL 含 Gogs 用户名片段（`--skip-remote-check` 可关）
- [x] **`--pack-pnms`**：覆盖默认 PNMS 目录（默认 `MMEM_PNMS_DATA_ROOT/<user>/<agent>/`）

## 联调（需本机环境，不自动 CI）

- [ ] 对真实 `MMEM_BASE_URL`：手动运行 `mmem doctor` + `mmem chat -m "hi" --llm mock`（`--no-remote` 已可离线验证 PNMS）
- [ ] `MMEM_INTEGRATION=1`（mindmemory 仓库）全链路：需 MySQL、Gogs、已注册账号与私钥

---

## workspace + 运行时清单（见 [docs/memory-repo-extended-layout.md](docs/memory-repo-extended-layout.md)）

设计目标：在 **`pnms/`**、**`repo/`** 同级增加 **`workspace/`**；用 **`workspace/.mmem-sync-manifest.json`**（**不入记忆 Git**）声明本次要打包进 **extras** 类密文的相对路径；上传/下载与现有 **`K_seed`**、**`mmem sync push`** / **`mmem memory merge`** 同一条同步故事，渐进落地。

### 目录与初始化

- [ ] `agent_workspace`：提供 **`agent_workspace_dir` / `resolve_workspace_dir_for_user_agent`**（或等价命名）指向 `<agent>/workspace/`，与 `pnms`、`repo` 同级
- [ ] **`mmem agent init`**（或 `ensure_default_agent_workspace`）：可选创建空 **`workspace/`**（及文档说明清单由调用方写入）
- [ ] 文档：`repo/.gitignore` 建议片段（避免误将 `../workspace` 绑进记忆仓）；在 `mmem-使用说明.md` 中同步「已实现」行为

### 清单 `.mmem-sync-manifest.json`

- [ ] 定义 **`schema_version`** 与 JSON Schema 或 dataclass（`bundles[]`：`id`、`include`、`optional` 等）
- [ ] 解析与校验：未知 `schema_version` 时明确报错或降级策略
- [ ] **路径安全**：`include` 仅允许相对 `workspace/` 的路径，拒绝 **`..`**、绝对路径、越界符号链接（按实现定策略）
- [ ] **`optional`**：缺失文件时跳过或失败的行为与日志

### 库 API（mindmemory_client）

- [ ] **`pack_workspace_extras_to_enc(manifest, workspace_root, key) -> bytes`**（或等价）：按 `include` 打 **tar.gz** → **`encrypt_memory_base64`**（与 `pnms_bundle.enc` 同管道）
- [ ] **`decrypt_extras_bundle_to_workspace(bundle_path, workspace_root, key, *, merge_policy=...)`**（或等价）：解密 → 解压到 `workspace/` 相对路径；**默认不覆盖** **`.mmem-sync-manifest.json`**（与文档 §4 一致）
- [ ] 与现有 **`memory_bundle`** / **`import_encrypted_bundle_to_agent_checkpoint`**（仅 PNMS）边界清晰：extras **不进** `pnms/` checkpoint 合并逻辑，仅落 **`workspace/`**

### `repo/` 内产物路径（与 §5 兼容）

- [ ] 固定首轮实现：例如根目录 **`extras_bundle.enc`** **或** **`mmem/bundles/extras.enc`**（二选一并写死文档，避免漂移）
- [ ] （可选，长期）**`mmem/repo.schema.json`**：声明仓内 bundles 列表与路径；push/merge 时校验

### CLI `mmem`

- [ ] **`mmem sync push`**：若存在支持的清单且 **`--sync-extras`**（或默认-on，需产品决策）则生成 extras 密文并 **`git add`** 与 **`pnms_bundle.enc`** 同批提交
- [ ] **`mmem memory merge`** / **`import-bundle`**：在现有 **`pnms_bundle.enc`** 流程之外，检测 extras 密文文件并解密解压到 **`workspace/`**（可与 `--import-extras` 开关配合）
- [ ] （可选）子命令或 flag：仅生成/校验清单、干跑列出将打入 tar 的路径

### 测试与安全

- [ ] 单元测试：清单解析、路径 sanitize、空清单、缺失 optional 文件、tar 内容与加密往返
- [ ] 集成测试（可选）：临时 git 仓库下 push 与 merge 双机路径的 smoke

### 宿主集成（库外，仅跟踪）

- [ ] Claw 记忆插件：启动时写清单 → 调库打包加密 → 走既有 sync；**不**在库内绑定 Claw
- [ ] （可选）**LLM 拼装**（文档 §6）：CLI 或插件侧将 **workspace 明文 / extras 解密结果** 与 PNMS **`get_context`** 按序拼接——**非**本库强制实现，属宿主责任
