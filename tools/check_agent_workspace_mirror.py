#!/usr/bin/env python3
"""校验 ``src/mindmemory_client/agent`` 与仓库根 ``agent/`` 下 BT-7274 workspace 镜像文件一致。

用法：``python tools/check_agent_workspace_mirror.py``（在 mindmemory-client 仓库根执行）。
退出码：0 一致，1 不一致或缺失。
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    src = root / "src" / "mindmemory_client" / "agent" / "BT-7274" / "workspace"
    mirror = root / "agent" / "BT-7274" / "workspace"
    if not src.is_dir():
        print(f"MISSING: {src}", file=sys.stderr)
        return 1
    if not mirror.is_dir():
        print(f"MISSING_MIRROR: {mirror}", file=sys.stderr)
        return 1
    names_src = sorted(p.name for p in src.iterdir() if p.is_file())
    names_m = sorted(p.name for p in mirror.iterdir() if p.is_file())
    if names_src != names_m:
        print(
            f"FILE_LIST_MISMATCH:\n  package: {names_src}\n  mirror:  {names_m}",
            file=sys.stderr,
        )
        return 1
    for name in names_src:
        bs = (src / name).read_bytes()
        bm = (mirror / name).read_bytes()
        if bs != bm:
            print(f"CONTENT_MISMATCH: {name}", file=sys.stderr)
            return 1
    print("OK: agent/BT-7274/workspace matches package data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
