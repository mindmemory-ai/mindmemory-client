"""与 mindmemory/tests/test_integration_flow.py 中 JSON 形状一致。"""

import json

from mindmemory_client.sync import (
    build_begin_submit_payload,
    build_mark_completed_payload,
)


def test_begin_submit_payload_json_parse():
    p = build_begin_submit_payload(
        "42052176-2140-4dea-80e6-c663239e77c2",
        "agent_test",
        ts=1700000000,
    )
    d = json.loads(p)
    assert d == {
        "ts": 1700000000,
        "op": "begin-submit",
        "user_uuid": "42052176-2140-4dea-80e6-c663239e77c2",
        "agent": "agent_test",
    }


def test_mark_completed_payload_json_parse():
    p = build_mark_completed_payload(
        "42052176-2140-4dea-80e6-c663239e77c2",
        "agent_test",
        "lock-uuid-1",
        "abc123deadbeef",
        ts=1700000001,
    )
    d = json.loads(p)
    assert d["op"] == "mark-completed"
    assert d["lock_uuid"] == "lock-uuid-1"
    assert d["commit"] == "abc123deadbeef"
