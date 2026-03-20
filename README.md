# mindmemory-client

Python 库与 `mmem` CLI：PNMS 长期记忆 + MindMemory `/api/v1`（含 sync 签名）。

开发安装需先安装同工作区的 `pnms`：

```bash
pip install -e ../pnms
pip install -e ".[dev]"
```

设计见 `docs/mindmemory-client-设计.md`。

默认大模型为本地 **Ollama**（`http://127.0.0.1:11434`）。多模型见 `docs/config.example.toml`，复制为 `~/.config/mmem/config.toml` 后使用 `mmem chat -p fast` 等切换 profile。
