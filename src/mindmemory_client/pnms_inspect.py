"""从 PNMS checkpoint 目录读取概念图 meta、graph.db 统计（不依赖 GPU）。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def concept_checkpoint_root(pnms_data_root: Path, user_uuid: str, agent_name: str) -> Path:
    """与 ``PnmsMemoryBridge`` / ``resolve_pnms_data_dir`` 一致的目录。"""
    from mindmemory_client.pnms_bridge import resolve_pnms_data_dir

    return resolve_pnms_data_dir(Path(pnms_data_root), user_uuid, agent_name)


def load_concept_meta(root: Path) -> dict[str, Any] | None:
    p = root / "meta.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def count_graph_edges(graph_db: Path) -> int | None:
    if not graph_db.is_file():
        return None
    try:
        conn = sqlite3.connect(str(graph_db))
        try:
            cur = conn.execute("SELECT COUNT(*) FROM edges")
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def top_graph_edges(graph_db: Path, limit: int) -> list[tuple[str, str, float]]:
    """按边权降序取前 ``limit`` 条（无向存储为规范化 (min,max)）。"""
    if not graph_db.is_file() or limit <= 0:
        return []
    try:
        conn = sqlite3.connect(str(graph_db))
        try:
            cur = conn.execute(
                "SELECT slot_i, slot_j, weight FROM edges ORDER BY weight DESC LIMIT ?",
                (limit,),
            )
            return [(str(r[0]), str(r[1]), float(r[2])) for r in cur.fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def count_saved_memory_slots(memory_slots_json: Path) -> int | None:
    """``memory_slots.json`` 中槽条数；文件不存在或格式异常时返回 None。"""
    if not memory_slots_json.is_file():
        return None
    try:
        raw = json.loads(memory_slots_json.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return len(raw)
        if isinstance(raw, dict) and isinstance(raw.get("slots"), list):
            return len(raw["slots"])
    except (OSError, json.JSONDecodeError):
        return None
    return None


def summarize_checkpoint_dir(root: Path) -> dict[str, Any]:
    """
    汇总磁盘上 ``save_concept_modules`` 写入的内容：概念、图边、记忆槽与会话状态。
    """
    out: dict[str, Any] = {
        "checkpoint_dir": str(root.resolve()),
        "exists": root.is_dir(),
        "meta": None,
        "concept_module_ids": [],
        "concept_pt_files": [],
        "graph_db": None,
        "graph_edge_count": None,
        "memory_slots_json": None,
        "memory_slots_saved_count": None,
        "memory_session_pt": None,
    }
    if not root.is_dir():
        return out

    meta = load_concept_meta(root)
    out["meta"] = meta
    if isinstance(meta, dict):
        mids = meta.get("module_ids")
        if isinstance(mids, list):
            out["concept_module_ids"] = [str(x) for x in mids]

    for mid in out["concept_module_ids"]:
        pt = root / f"{mid}.pt"
        if pt.is_file():
            out["concept_pt_files"].append({"id": mid, "path": str(pt), "bytes": pt.stat().st_size})

    gdb = root / "graph.db"
    if gdb.is_file():
        out["graph_db"] = str(gdb.resolve())
        out["graph_edge_count"] = count_graph_edges(gdb)
    else:
        out["graph_edge_count"] = None

    ms = root / "memory_slots.json"
    if ms.is_file():
        out["memory_slots_json"] = str(ms.resolve())
        out["memory_slots_saved_count"] = count_saved_memory_slots(ms)
    mss = root / "memory_session.pt"
    if mss.is_file():
        out["memory_session_pt"] = str(mss.resolve())

    return out
