"""``mmem pnms``：查看本地 PNMS checkpoint（概念模块 + 记忆图）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from mindmemory_client.agent_workspace import resolve_pnms_dir_for_user_agent
from mindmemory_client.client_state import resolve_mmem_config
from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.pnms_inspect import (
    load_concept_meta,
    summarize_checkpoint_dir,
    top_graph_edges,
)

pnms_app = typer.Typer(no_args_is_help=True, help="PNMS 概念图与记忆图（磁盘 checkpoint）")


def _resolve_root(
    *,
    base_url: Optional[str],
    agent: str,
    user_uuid: Optional[str],
) -> tuple[str, Path, MindMemoryClientConfig]:
    cfg = resolve_mmem_config(base_url_override=base_url, agent_name_override=agent)
    uid = user_uuid or cfg.user_uuid or "local-dev-user"
    root = resolve_pnms_dir_for_user_agent(cfg, uid, agent)
    return uid, root, cfg


@pnms_app.command("status")
def pnms_status(
    agent: str = typer.Option("cli-agent", "--agent", help="与 mmem chat 一致的 Agent 名"),
    user_uuid: Optional[str] = typer.Option(
        None,
        "--user",
        help="覆盖 user_uuid（默认：已登录账户或 local-dev-user）",
    ),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """查看当前 user+agent 的 checkpoint 目录与已保存的概念/图统计。"""
    uid, root, cfg = _resolve_root(base_url=base_url, agent=agent, user_uuid=user_uuid)
    summary = summarize_checkpoint_dir(root)

    if json_out:
        payload = {
            "user_uuid": uid,
            "agent": agent,
            "pnms_data_root": str(cfg.pnms_data_root),
            **summary,
            "note": "PNMS 在 save_checkpoint 时会写入 memory_slots.json 与 memory_session.pt（含 S_t 与 round_counter）。",
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"user_uuid: {uid}")
    typer.echo(f"agent: {agent}")
    typer.echo(f"PNMS 数据根: {cfg.pnms_data_root}")
    typer.echo(f"checkpoint 目录: {summary['checkpoint_dir']}")
    if not summary["exists"]:
        typer.echo("状态: 目录不存在（尚未在本机保存过概念/图）")
        return

    typer.echo("状态: 目录存在")
    meta = summary.get("meta")
    if isinstance(meta, dict):
        typer.echo(
            f"meta.json: embed_dim={meta.get('embed_dim')} concept_dim={meta.get('concept_dim')} "
            f"top_m={meta.get('top_m')}"
        )
    else:
        typer.echo("meta.json: 无（尚未保存概念模块）")

    mids = summary.get("concept_module_ids") or []
    typer.echo(f"已保存概念模块数: {len(mids)}  ids={mids!r}")
    n_edge = summary.get("graph_edge_count")
    if n_edge is None:
        typer.echo("graph.db: 无文件")
    else:
        typer.echo(f"graph.db: 边数={n_edge}")

    n_mem = summary.get("memory_slots_saved_count")
    if n_mem is not None:
        typer.echo(f"memory_slots.json: 已保存槽数={n_mem}")
    elif (root / "memory_slots.json").is_file():
        typer.echo("memory_slots.json: 存在（条数解析失败）")
    else:
        typer.echo("memory_slots.json: 无（尚未经 save_checkpoint 写入记忆槽）")
    if summary.get("memory_session_pt"):
        typer.echo(f"memory_session.pt: 存在（个人状态 S_t 与轮次）")
    else:
        typer.echo("memory_session.pt: 无")

    typer.echo(
        "说明: 每轮对话结束会 save_checkpoint，落盘概念、图、记忆槽与个人状态；"
        "下次启动 mmem chat 会从同目录恢复。"
    )


@pnms_app.command("concepts")
def pnms_concepts(
    agent: str = typer.Option("cli-agent", "--agent"),
    user_uuid: Optional[str] = typer.Option(None, "--user"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """列出已保存的概念模块（meta.json + 各 .pt 文件）。"""
    uid, root, _cfg = _resolve_root(base_url=base_url, agent=agent, user_uuid=user_uuid)
    meta = load_concept_meta(root)

    if json_out:
        summary = summarize_checkpoint_dir(root)
        typer.echo(json.dumps({"user_uuid": uid, "agent": agent, **summary}, ensure_ascii=False, indent=2))
        return

    typer.echo(f"checkpoint: {root.resolve()}")
    if not meta:
        typer.echo("尚无 meta.json（未保存过概念模块）。")
        return

    typer.echo(json.dumps(meta, ensure_ascii=False, indent=2))
    for mid in meta.get("module_ids") or []:
        pt = root / f"{mid}.pt"
        if pt.is_file():
            typer.echo(f"  - {mid}: {pt.name} ({pt.stat().st_size} bytes)")
        else:
            typer.echo(f"  - {mid}: 缺少 {mid}.pt", err=True)


@pnms_app.command("graph")
def pnms_graph(
    agent: str = typer.Option("cli-agent", "--agent"),
    user_uuid: Optional[str] = typer.Option(None, "--user"),
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
    limit: int = typer.Option(30, "--limit", "-n", help="列出边权最高的前 N 条"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """查看已保存的记忆图边（SQLite graph.db，按边权降序）。"""
    _uid, root, _cfg = _resolve_root(base_url=base_url, agent=agent, user_uuid=user_uuid)
    gdb = root / "graph.db"

    edges = top_graph_edges(gdb, limit=max(0, limit))

    if json_out:
        typer.echo(
            json.dumps(
                {"checkpoint": str(root.resolve()), "graph_db": str(gdb), "edges": [{"slot_i": a, "slot_j": b, "weight": w} for a, b, w in edges]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(f"graph.db: {gdb.resolve()}")
    if not gdb.is_file():
        typer.echo("文件不存在（尚未保存过图）。")
        return

    typer.echo(f"显示至多 {limit} 条边（按 weight 降序）:")
    for a, b, w in edges:
        typer.echo(f"  {a} — {b}  w={w:.4f}")
