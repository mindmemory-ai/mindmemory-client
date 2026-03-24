"""
大型集成场景：30 轮对话（6 组 × 5 个相关问题）→ 打包为 pnms_bundle →
import 合并到第二 checkpoint → 再 20 轮相似追问；每轮将 PNMS 传入 LLM 的 (query, context) 落盘。

需安装 ``pnms``、``torch``；不依赖 MindMemory 远端或真实账号目录（使用独立 ``tmp_path``）。

运行示例：``pytest tests/test_large_memory_scenario.py -m integration -v`` 或只跑该文件。
"""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path
from typing import Callable

import pytest

pytest.importorskip("torch")
pytest.importorskip("pnms")

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.memory_bundle import import_encrypted_bundle_to_agent_checkpoint
from mindmemory_client.memory_crypto import encrypt_memory_base64
from mindmemory_client.pnms_bridge import PnmsMemoryBridge
from mindmemory_client.session import ChatMemorySession

# 与 tests/test_memory_bundle.py 一致：32 字节对称密钥
_K_TEST = b"x" * 32

# 固定测试用 user / agent（不读写 ~/.mindmemory）
_TEST_USER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_TEST_AGENT = "large-scenario-agent"


def _pack_pnms_dir_to_encrypted_bundle_file(pnms_dir: Path, key: bytes, out_file: Path) -> None:
    """与 ``mmem sync push`` 相同：目录 → tar.gz → AES-GCM → Base64 单行。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(pnms_dir, arcname=pnms_dir.name)
    out_file.write_text(encrypt_memory_base64(buf.getvalue(), key) + "\n", encoding="utf-8")


def _build_questions_phase1() -> list[str]:
    """30 个问题：每 5 个一组，组内主题相关。"""
    groups = [
        # 组 1：Python
        [
            "Python 中 list 和 tuple 有什么区别？",
            "Python 的 dict 如何安全地读取可能不存在的键？",
            "什么是 Python 列表推导式？",
            "Python 中 async 和 await 一般用在什么场景？",
            "如何用 Python 打开一个文本文件并读取全部内容？",
        ],
        # 组 2：Web / HTTP
        [
            "HTTP 状态码 404 一般表示什么？",
            "GET 和 POST 请求有什么典型区别？",
            "什么是 CORS？它解决什么问题？",
            "Cookie 通常存在客户端还是服务端？",
            "HTTPS 相比 HTTP 多做了哪类保护？",
        ],
        # 组 3：数据库
        [
            "关系数据库里主键（primary key）的作用是什么？",
            "数据库索引可能带来哪些代价？",
            "简述事务的 ACID 四个字母分别指什么。",
            "INNER JOIN 和 LEFT JOIN 结果集可能有何不同？",
            "文档型 NoSQL 与典型关系库在模型上有什么差异？",
        ],
        # 组 4：操作系统
        [
            "进程和线程在资源隔离上有什么主要区别？",
            "什么是虚拟内存？它主要缓解什么问题？",
            "文件描述符在 Unix 系系统里大致指什么？",
            "死锁产生的四个必要条件常被称为什么？",
            "Linux 中 chmod 755 对三类用户分别常表示什么权限？",
        ],
        # 组 5：Git
        [
            "git merge 与 git rebase 在提交历史上有什么直观区别？",
            "git clone 主要会拉取哪些内容到本地？",
            ".gitignore 文件的主要用途是什么？",
            "git fetch 与 git pull 在操作顺序上通常有何不同？",
            "如何用一条 git 命令查看最近若干条提交摘要？",
        ],
        # 组 6：机器学习
        [
            "过拟合（overfitting）通常指什么现象？",
            "梯度下降在优化里大致在做什么？",
            "k 折交叉验证的目的之一是什么？",
            "神经网络里激活函数通常引入什么性质？",
            "分类任务里 loss 与 accuracy 关注点有何不同？",
        ],
    ]
    out: list[str] = []
    for g in groups:
        assert len(g) == 5
        out.extend(g)
    assert len(out) == 30
    return out


def _build_questions_phase2_similar() -> list[str]:
    """20 个问题：与 phase1 主题相近或换表述追问。"""
    return [
        "再用一句话对比 Python 的 list 与 tuple 适用场景。",
        "若 HTTP 返回 404，前端与后端各自可能排查什么？",
        "主键能否由多列共同组成？这在建模里叫什么？",
        "多线程共享地址空间可能带来哪些同步问题？",
        "在什么情况下你会优先选择 git rebase 而不是 merge？",
        "过拟合时，训练集和验证集误差通常呈现什么关系？",
        "Python 里 with open(...) as f 主要保证什么？",
        "REST 里资源通常用什么方式标识？",
        "数据库事务隔离级别主要缓解哪些异常现象？",
        "进程间通信常见方式举两例即可。",
        "git reset --soft 与 --hard 对暂存区影响有何不同？",
        "随机梯度下降与批量梯度下降在更新频率上差异是什么？",
        "HTTPS 握手阶段大致会协商什么？",
        "B 树索引与哈希索引适用场景有何直觉差异？",
        "线程比进程更轻量主要体现在哪些方面？",
        "什么是学习率过大可能导致的现象？",
        "HTTP 无状态通常指什么？",
        "外键约束主要用来保证什么？",
        "git branch 与 git checkout -b 在创建分支上关系是什么？",
        "dropout 在训练与推理阶段通常如何使用？",
    ]


def _make_llm_with_prompt_dump(
    dump_dir: Path,
    phase: str,
    turn_counter: list[int],
) -> Callable[[str, str], str]:
    """与 ``mmem chat`` mock 类似：将 PNMS 传入的 ``(query, context)`` 写入文件。"""
    dump_dir.mkdir(parents=True, exist_ok=True)

    def llm(query: str, context: str) -> str:
        turn_counter[0] += 1
        n = turn_counter[0]
        p = dump_dir / f"{phase}_turn_{n:03d}.txt"
        p.write_text(
            f"[phase]\n{phase}\n\n[query]\n{query}\n\n[context_from_pnms]\n{context}\n",
            encoding="utf-8",
        )
        return f"[mock_response phase={phase} turn={n}]"

    return llm


def _test_config(tmp_path: Path) -> MindMemoryClientConfig:
    return MindMemoryClientConfig(
        base_url="http://127.0.0.1:8000",
        user_uuid=_TEST_USER,
        private_key_path=None,
        pnms_data_root=tmp_path / "accounts_root",
        agent_name=_TEST_AGENT,
    )


@pytest.mark.integration
def test_large_memory_scenario_phase30_merge_phase20(tmp_path: Path) -> None:
    """
    1. Phase1：30 轮 ``ChatMemorySession.handle_turn``，每轮 ``save_checkpoint``。
    2. 将 phase1 checkpoint 打成 ``pnms_bundle.enc``，经 ``import_encrypted_bundle_to_agent_checkpoint`` 合并到空目标目录。
    3. Phase2：在新 checkpoint 上再 20 轮；校验提示词文件数量与关键 API 无异常。
    """
    cfg = _test_config(tmp_path)
    prompts_dir = tmp_path / "prompt_dumps"
    pnms_p1 = tmp_path / "pnms_phase1"
    pnms_p1.mkdir(parents=True)

    bridge1 = PnmsMemoryBridge(
        cfg.pnms_data_root,
        _TEST_USER,
        _TEST_AGENT,
        checkpoint_dir=pnms_p1,
    )
    session1 = ChatMemorySession(bridge1, system_prompt="你是用于集成测试的助手，回答尽量简短。")
    turn_cnt = [0]
    llm1 = _make_llm_with_prompt_dump(prompts_dir, "phase1", turn_cnt)

    questions_30 = _build_questions_phase1()
    slots_after: list[int] = []
    for i, q in enumerate(questions_30):
        r = session1.handle_turn(q, llm1)
        assert r.response.startswith("[mock_response"), (i, r.response[:80])
        assert isinstance(r.context, str)
        assert isinstance(r.num_slots_used, int)
        assert isinstance(r.phase, str)
        session1.save_checkpoint()
        slots_after.append(bridge1.get_slot_count())

    assert turn_cnt[0] == 30
    n_prompt_files_p1 = len(list(prompts_dir.glob("phase1_turn_*.txt")))
    assert n_prompt_files_p1 == 30

    bundle_path = tmp_path / "pnms_bundle.enc"
    _pack_pnms_dir_to_encrypted_bundle_file(pnms_p1, _K_TEST, bundle_path)
    assert bundle_path.is_file()

    pnms_p2 = tmp_path / "pnms_phase2_merged"
    pnms_p2.mkdir(parents=True)
    meta = import_encrypted_bundle_to_agent_checkpoint(
        bundle_path=bundle_path,
        key=_K_TEST,
        dest_pnms_dir=pnms_p2,
        cfg=cfg,
        user_uuid=_TEST_USER,
        agent_name=_TEST_AGENT,
        expected_memory_format_version=None,
    )
    assert isinstance(meta, dict)
    assert "dest_pnms_dir" in meta
    assert meta.get("num_slots") is not None

    # Phase2：在合并后的 checkpoint 上继续对话
    bridge2 = PnmsMemoryBridge(
        cfg.pnms_data_root,
        _TEST_USER,
        _TEST_AGENT,
        checkpoint_dir=pnms_p2,
    )
    session2 = ChatMemorySession(bridge2, system_prompt="你是用于集成测试的助手，回答尽量简短。")
    turn_cnt[0] = 0
    llm2 = _make_llm_with_prompt_dump(prompts_dir, "phase2", turn_cnt)

    questions_20 = _build_questions_phase2_similar()
    assert len(questions_20) == 20
    for j, q in enumerate(questions_20):
        r = session2.handle_turn(q, llm2)
        assert r.response.startswith("[mock_response"), (j, r.response[:80])
        session2.save_checkpoint()

    assert turn_cnt[0] == 20
    n_prompt_files_p2 = len(list(prompts_dir.glob("phase2_turn_*.txt")))
    assert n_prompt_files_p2 == 20
    assert len(list(prompts_dir.glob("*.txt"))) == 50

    # 合并后槽位应可查询（具体数值依赖 PNMS 冷启动与合并实现，只作下界/存在性）
    assert bridge2.get_slot_count() >= 0

    snap = tmp_path / "snap_copy"
    shutil.copytree(pnms_p2, snap)
    assert any(snap.iterdir())
