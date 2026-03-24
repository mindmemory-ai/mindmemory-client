"""
可选集成 smoke：临时 git 仓库 + workspace 清单 → extras.enc → commit → 解密回写。

无需 MindMemory / Gogs；需本机 ``git`` 可用。
"""

from __future__ import annotations

import subprocess

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from mindmemory_client.register_crypto import k_seed_bytes_from_private_key_openssh
from mindmemory_client.workspace_extras import (
    decrypt_extras_bundle_file_to_workspace,
    pack_workspace_extras_from_manifest_file,
)


def _have_git() -> bool:
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not _have_git(), reason="git not available")
def test_workspace_extras_git_commit_and_decrypt_roundtrip(tmp_path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo.mkdir()
    workspace.mkdir(parents=True)

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "smoke@test.local"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "mmem-smoke"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (workspace / "p").mkdir()
    (workspace / "p" / "a.txt").write_text("hello-smoke", encoding="utf-8")
    cfg = workspace / "mmem-workspace.json"
    cfg.write_text(
        '{"schema_version":"2","sync":{"bundles":[{"id":"extras","include":["p/a.txt"],"optional":false}]}}',
        encoding="utf-8",
    )

    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        Encoding.PEM,
        PrivateFormat.OpenSSH,
        NoEncryption(),
    ).decode("utf-8")
    key = k_seed_bytes_from_private_key_openssh(pem)

    b64 = pack_workspace_extras_from_manifest_file(cfg, workspace, key)
    dest = repo / "mmem" / "bundles" / "extras.enc"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(b64 + "\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "mmem/bundles/extras.enc"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "smoke: extras bundle"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    tracked = subprocess.check_output(["git", "-C", str(repo), "ls-files"], text=True)
    assert "mmem/bundles/extras.enc" in tracked

    ws_out = tmp_path / "workspace_import"
    ws_out.mkdir()
    meta = decrypt_extras_bundle_file_to_workspace(dest, ws_out, key)
    assert (ws_out / "p" / "a.txt").read_text(encoding="utf-8") == "hello-smoke"
    assert "p/a.txt" in meta["written"]
