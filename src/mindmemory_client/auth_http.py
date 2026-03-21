"""MindMemory ``/api/v1/auth`` 无签名 HTTP 调用（注册、登录、上传公钥）。"""

from __future__ import annotations

from typing import Any

import httpx

from mindmemory_client.errors import MindMemoryAPIError


def _api_root(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/v1"


def _raise(r: httpx.Response) -> None:
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


def post_register(base_url: str, email: str, password: str, timeout_s: float = 60.0) -> dict[str, Any]:
    r = httpx.post(
        f"{_api_root(base_url)}/auth/register",
        json={"email": email, "password": password},
        timeout=timeout_s,
    )
    _raise(r)
    return r.json() if r.content else {}


def post_setup_key(
    base_url: str,
    email: str,
    public_key: str,
    encrypted_private_key_backup: str,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    r = httpx.post(
        f"{_api_root(base_url)}/auth/setup-key",
        json={
            "email": email,
            "public_key": public_key.strip(),
            "encrypted_private_key_backup": encrypted_private_key_backup,
        },
        timeout=timeout_s,
    )
    _raise(r)
    return r.json() if r.content else {}


def post_login(base_url: str, email: str, password: str, timeout_s: float = 60.0) -> dict[str, Any]:
    r = httpx.post(
        f"{_api_root(base_url)}/auth/login",
        json={"email": email, "password": password},
        timeout=timeout_s,
    )
    _raise(r)
    return r.json() if r.content else {}
