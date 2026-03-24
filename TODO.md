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
