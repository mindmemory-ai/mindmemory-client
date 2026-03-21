"""MindMemory HTTP `/api/v1` 客户端。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.errors import MindMemoryAPIError
from mindmemory_client.keys import load_ed25519_private_key
from mindmemory_client.sync import (
    build_begin_submit_payload,
    build_mark_completed_payload,
    sign_payload,
)


class MmemApiClient:
    def __init__(self, config: MindMemoryClientConfig):
        self._config = config
        self._root = config.base_url.rstrip("/")
        self._api = f"{self._root}/api/v1"
        self._client = httpx.Client(timeout=config.timeout_s)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MmemApiClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        url = f"{self._root}/health"
        logger.debug("GET %s", url)
        r = self._client.get(url)
        if r.status_code != 200:
            raise MindMemoryAPIError(
                f"health 失败: {r.status_code}", status_code=r.status_code, detail=r.text
            )
        return r.json() if r.content else {}

    def get_me(self, user_uuid: str) -> dict[str, Any]:
        url = f"{self._api}/me"
        logger.debug("GET %s", url)
        r = self._client.get(
            url,
            headers={"X-User-UUID": user_uuid},
        )
        self._raise_for_status(r)
        return r.json()

    def list_agents(self, user_uuid: str) -> dict[str, Any]:
        url = f"{self._api}/agents"
        logger.debug("GET %s", url)
        r = self._client.get(
            url,
            headers={"X-User-UUID": user_uuid},
        )
        self._raise_for_status(r)
        return r.json()

    def get_encrypted_private_key_backup(self, user_uuid: str) -> dict[str, Any]:
        """换机恢复：获取注册时上传的私钥备份密文（opaque JSON）。"""
        url = f"{self._api}/me/encrypted-private-key-backup"
        logger.debug("GET %s", url)
        r = self._client.get(
            url,
            headers={"X-User-UUID": user_uuid},
        )
        self._raise_for_status(r)
        return r.json()

    def begin_submit(
        self,
        user_uuid: str,
        agent_name: str,
        holder_info: str | None = None,
    ) -> dict[str, Any]:
        path = self._config.private_key_path
        if not path:
            raise ValueError("begin_submit 需要配置 private_key_path")
        priv = load_ed25519_private_key(path)
        payload = build_begin_submit_payload(user_uuid, agent_name)
        sig = sign_payload(payload, priv)
        body: dict[str, Any] = {
            "user_uuid": user_uuid,
            "agent_name": agent_name,
            "payload": payload,
            "signature": sig,
        }
        if holder_info is not None:
            body["holder_info"] = holder_info
        url = f"{self._api}/sync/begin-submit"
        logger.debug("POST %s", url)
        r = self._client.post(url, json=body)
        self._raise_for_status(r)
        return r.json()

    def mark_completed(
        self,
        user_uuid: str,
        agent_name: str,
        lock_uuid: str,
        submission_ok: bool,
        commit_ids: list[str] | None,
        error_message: str | None,
        *,
        commit_for_payload: str = "",
    ) -> dict[str, Any]:
        """commit_for_payload：签名 JSON 中的 commit 字段；无提交时传空串。"""
        path = self._config.private_key_path
        if not path:
            raise ValueError("mark_completed 需要配置 private_key_path")
        priv = load_ed25519_private_key(path)
        payload = build_mark_completed_payload(
            user_uuid, agent_name, lock_uuid, commit_for_payload or ""
        )
        sig = sign_payload(payload, priv)
        url = f"{self._api}/sync/mark-completed"
        logger.debug("POST %s", url)
        r = self._client.post(
            url,
            json={
                "user_uuid": user_uuid,
                "agent_name": agent_name,
                "lock_uuid": lock_uuid,
                "submission_ok": submission_ok,
                "error_message": error_message,
                "commit_ids": commit_ids or [],
                "payload": payload,
                "signature": sig,
            },
        )
        self._raise_for_status(r)
        return r.json()

    def _raise_for_status(self, r: httpx.Response) -> None:
        if r.is_success:
            return
        detail = r.text
        try:
            j = r.json()
            if isinstance(j, dict) and "detail" in j:
                detail = str(j["detail"])
        except Exception:
            pass
        raise MindMemoryAPIError(
            f"HTTP {r.status_code}: {detail}",
            status_code=r.status_code,
            detail=detail,
        )
