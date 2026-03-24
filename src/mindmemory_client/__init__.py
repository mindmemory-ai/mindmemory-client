"""MindMemory 客户端库：记忆引擎（pnms 仅在后端模块导入）+ MMEM HTTP API。"""

from mindmemory_client.api import MmemApiClient
from mindmemory_client.config import DEFAULT_AGENT_NAME, MindMemoryClientConfig
from mindmemory_client.errors import MindMemoryAPIError
from mindmemory_client.keys import read_openssh_private_key_pem
from mindmemory_client.memory_bundle import (
    format_memory_engine_error,
    import_encrypted_bundle_to_agent_checkpoint,
)
from mindmemory_client.memory_crypto import (
    decrypt_memory_base64,
    decrypt_memory_payload,
    encrypt_memory_base64,
    encrypt_memory_payload,
)
from mindmemory_client.memory_errors import MemoryEngineError
from mindmemory_client.memory_types import ChatTurnResult
from mindmemory_client.pnms_bridge import (
    PnmsMemoryBridge,
    is_memory_engine_available,
    peek_checkpoint_version_info,
    resolve_pnms_data_dir,
)
from mindmemory_client.register_crypto import (
    encrypted_password_hex_from_private_key_openssh,
    key_fingerprint_from_public_key_ssh,
    k_seed_bytes_from_private_key_openssh,
)
from mindmemory_client.session import ChatMemorySession
from mindmemory_client.sync_manifest import (
    MANIFEST_FILENAME,
    EXTRAS_BUNDLE_REPO_RELPATH,
    SyncManifest,
    SyncManifestError,
    load_sync_manifest,
)
from mindmemory_client.workspace_extras import (
    decrypt_extras_bundle_file_to_workspace,
    dry_run_workspace_extras_paths,
    pack_workspace_extras_to_enc,
)
from mindmemory_client.client_home import default_client_home
from mindmemory_client.client_state import resolve_mmem_config
from mindmemory_client.credential_source import credential_source
from mindmemory_client.settings import ClientEnvSettings, get_client_settings
from mindmemory_client.logging_config import configure_client_logging

__all__ = [
    "MindMemoryClientConfig",
    "DEFAULT_AGENT_NAME",
    "MindMemoryAPIError",
    "MemoryEngineError",
    "ChatTurnResult",
    "MmemApiClient",
    "PnmsMemoryBridge",
    "is_memory_engine_available",
    "peek_checkpoint_version_info",
    "resolve_pnms_data_dir",
    "import_encrypted_bundle_to_agent_checkpoint",
    "format_memory_engine_error",
    "ChatMemorySession",
    "read_openssh_private_key_pem",
    "key_fingerprint_from_public_key_ssh",
    "k_seed_bytes_from_private_key_openssh",
    "encrypted_password_hex_from_private_key_openssh",
    "encrypt_memory_payload",
    "decrypt_memory_payload",
    "encrypt_memory_base64",
    "decrypt_memory_base64",
    "default_client_home",
    "resolve_mmem_config",
    "ClientEnvSettings",
    "get_client_settings",
    "credential_source",
    "configure_client_logging",
    "MANIFEST_FILENAME",
    "EXTRAS_BUNDLE_REPO_RELPATH",
    "SyncManifest",
    "SyncManifestError",
    "load_sync_manifest",
    "pack_workspace_extras_to_enc",
    "dry_run_workspace_extras_paths",
    "decrypt_extras_bundle_file_to_workspace",
]
