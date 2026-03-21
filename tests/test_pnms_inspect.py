import json
import sqlite3
from pathlib import Path

from mindmemory_client.pnms_inspect import (
    count_graph_edges,
    load_concept_meta,
    summarize_checkpoint_dir,
    top_graph_edges,
)


def test_summarize_checkpoint_dir_empty(tmp_path: Path) -> None:
    root = tmp_path / "ckpt"
    s = summarize_checkpoint_dir(root)
    assert s["exists"] is False
    assert s["graph_edge_count"] is None


def test_summarize_with_meta_and_graph(tmp_path: Path) -> None:
    root = tmp_path / "ckpt"
    root.mkdir()
    (root / "meta.json").write_text(
        json.dumps(
            {"embed_dim": 8, "concept_dim": 32, "top_m": 2, "module_ids": ["m1", "m2"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "m1.pt").write_bytes(b"x")
    conn = sqlite3.connect(str(root / "graph.db"))
    try:
        conn.execute(
            "CREATE TABLE edges (slot_i TEXT NOT NULL, slot_j TEXT NOT NULL, weight REAL NOT NULL, PRIMARY KEY (slot_i, slot_j))"
        )
        conn.execute("INSERT INTO edges VALUES ('a','b',0.5)")
        conn.execute("INSERT INTO edges VALUES ('a','c',0.9)")
        conn.commit()
    finally:
        conn.close()

    s = summarize_checkpoint_dir(root)
    assert s["exists"] is True
    assert s["graph_edge_count"] == 2
    assert len(s["concept_pt_files"]) == 1
    assert load_concept_meta(root)["module_ids"] == ["m1", "m2"]
    assert count_graph_edges(root / "graph.db") == 2
    edges = top_graph_edges(root / "graph.db", 10)
    assert len(edges) == 2
    assert edges[0][2] >= edges[1][2]
