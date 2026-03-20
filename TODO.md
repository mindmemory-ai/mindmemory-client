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
- [x] 单元测试：`tests/test_sync_payload.py`

## CLI `mmem`

- [x] `mmem doctor` — 检查导入、`GET /health`、配置项存在性（不打印密钥）
- [x] `mmem chat` — REPL / `-m`；`--llm mock|echo`；`--no-remote`；可选 `--sync-after` 在每轮后 begin+mark（无 git 时 `submission_ok=false` 或跳过）
- [ ] `mmem chat` — `--llm ollama` / OpenAI 兼容（后续）
- [ ] `mmem sync push` — 加密 + git worktree（与 openclaw-mmem 对齐，后续）

## 联调

- [ ] 对真实 `MMEM_BASE_URL`：`doctor` + `chat -m "hi" --llm mock`（`--no-remote` 已可离线）
- [ ] `MMEM_INTEGRATION=1` 全链路（需私钥与注册账号）
