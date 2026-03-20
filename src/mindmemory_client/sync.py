"""Sync API：payload 格式与 mindmemory/tests/test_integration_flow.py 一致。"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def build_begin_submit_payload(
    user_uuid: str,
    agent_name: str,
    ts: int | None = None,
) -> str:
    t = int(time.time()) if ts is None else ts
    return f'{{"ts":{t},"op":"begin-submit","user_uuid":"{user_uuid}","agent":"{agent_name}"}}'


def build_mark_completed_payload(
    user_uuid: str,
    agent_name: str,
    lock_uuid: str,
    commit_id: str,
    ts: int | None = None,
) -> str:
    t = int(time.time()) if ts is None else ts
    return (
        f'{{"ts":{t},"op":"mark-completed","user_uuid":"{user_uuid}",'
        f'"agent":"{agent_name}","lock_uuid":"{lock_uuid}","commit":"{commit_id}"}}'
    )


def sign_payload(payload: str, private_key: Ed25519PrivateKey) -> str:
    sig = private_key.sign(payload.encode("utf-8"))
    return base64.b64encode(sig).decode("ascii")
