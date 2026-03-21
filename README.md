# mindmemory-client

Python 库与 `mmem` CLI：PNMS 长期记忆 + MindMemory `/api/v1`（含 sync 签名）。

开发安装需先安装同工作区的 `pnms`：

```bash
pip install -e ../pnms
pip install -e ".[dev]"
```

设计见 `docs/mindmemory-client-设计.md`。

**同步**：`mmem sync push` 仅向 Git 提交加密后的 **`pnms_bundle.enc`**（PNMS 数据目录）。推送前会 `git fetch` 并与远端比较；若远端较新或分叉，请先执行 **`mmem memory merge`**（当前仅 Git 层 rebase，PNMS 合并待库支持）。

默认大模型为本地 **Ollama**（`http://127.0.0.1:11434`）。多模型见 `docs/config.example.toml`，复制为 `~/.config/mmem/config.toml` 后使用 `mmem chat -p fast` 等切换 profile。
