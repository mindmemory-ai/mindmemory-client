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
- [x] 单元测试：`tests/test_sync_payload.py`、`tests/test_llm_profiles.py`
- [x] `llm_profiles` + `ollama_llm`：默认 Ollama；`~/.config/mmem/config.toml` 多 profile；环境变量覆盖

### 加密与注册材料（见设计文档 §11、`mindmemory/tools/gen_register_bundle.py`）

- [ ] `crypto` 或 `keys` 扩展：`key_fingerprint_from_public_key_ssh()` — 与 `_ssh_pubkey_blob_sha256_hex` 一致
- [ ] `k_seed_bytes_from_private_key_openssh()` — `SHA256(privkey_pem_utf8)` 原始 32 字节；`encrypted_password_hex()` — 与 `gen_register_bundle.py` 字节级一致（单元测试对照官方脚本）
- [ ] **AES-256-GCM 密钥 = `K_seed` 32 字节**（全用户各 Agent 统一，见 §11.1）
- [ ] 记忆载荷格式：12 字节 nonce，`nonce‖ciphertext‖tag` → Base64，与 `openclaw-mmem/docs/mmem记忆文件结构.md` 一致

## CLI `mmem`

- [x] `mmem doctor` — 依赖、MindMemory、Ollama（`/api/tags`）
- [x] `mmem chat` — 默认 `--llm ollama`；`--profile` / `-p`；`--ollama-url`、`--model`；`mock`/`echo`；`--no-remote`
- [x] `mmem models` — 列出已加载 profile
- [ ] **`mmem sync push`** — 完整闭环：  
  - [ ] 从私钥重算 `encrypted_password` / `K_seed`（与 bundle 工具一致）  
  - [ ] 序列化 PNMS（或约定切片）→ `P_mem` / HKDF → **AES-256-GCM** → 写入本地 git 工作树  
  - [ ] `git commit` / `git push` 至远端分支（`memory_schema_version`）  
  - [ ] `begin-submit` → push → `mark-completed`（`commit_ids`）  
  - [ ] 与 `mindmemory/mmem.md` 3.3、`openclaw-mmem` 记忆文件结构对齐

## 联调

- [ ] 对真实 `MMEM_BASE_URL`：`doctor` + `chat -m "hi" --llm mock`（`--no-remote` 已可离线）
- [ ] `MMEM_INTEGRATION=1` 全链路（需私钥与注册账号）
