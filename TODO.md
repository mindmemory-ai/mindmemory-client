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
- [x] `llm_profiles` + `ollama_llm`：默认 Ollama；`~/.config/mmem/config.toml` 多 profile；环境变量覆盖

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
- [x] **`mmem sync push`** — begin-submit → 写 `mmem_payload.enc` → git add/commit/push → mark-completed（需 `--git-dir`）；无 `--git-dir` 仅生成本地密文
- [ ] **增强**：push 前 `pull --rebase`、冲突处理；PNMS 目录打包进 bundle；与 Gogs 远端 URL 校验

## 联调

- [ ] 对真实 `MMEM_BASE_URL`：`doctor` + `chat -m "hi" --llm mock`（`--no-remote` 已可离线）
- [ ] `MMEM_INTEGRATION=1` 全链路（需私钥与注册账号）
