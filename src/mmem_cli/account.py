"""mmem account：多账户、注册、登录、登出。"""

from __future__ import annotations

import getpass
from typing import Optional

import typer

from mindmemory_client.api import MmemApiClient
from mindmemory_client.auth_http import post_login, post_register, post_setup_key
from mindmemory_client.client_paths import (
    account_private_key_path,
    client_config_dir,
    client_data_dir,
    default_pnms_data_root,
)
from mindmemory_client.client_state import (
    AccountMeta,
    ensure_client_dirs,
    find_account_by_email,
    has_local_private_key,
    list_local_accounts,
    load_state,
    resolve_mmem_config,
    save_account_meta,
    save_state,
    write_private_key_file,
)
from mindmemory_client.credential_source import credential_source
from mindmemory_client.config import MindMemoryClientConfig
from mindmemory_client.errors import MindMemoryAPIError
from mindmemory_client.keygen import generate_ed25519_openssh_keypair
from mindmemory_client.keys import load_ed25519_private_key
from mindmemory_client.private_key_backup import (
    decrypt_private_key_backup_openssh,
    encrypt_private_key_backup_openssh,
)

account_app = typer.Typer(help="多账户：注册、登录、切换、当前用户")


def _validate_password_local(password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码至少 8 位")
    if not any(c.isalpha() for c in password):
        raise ValueError("密码需包含字母")
    if not any(c.isdigit() for c in password):
        raise ValueError("密码需包含数字")


def _prompt_email() -> str:
    return typer.prompt("邮箱").strip().lower()


def _base_cfg(base_url: Optional[str]) -> MindMemoryClientConfig:
    cfg = MindMemoryClientConfig.from_env()
    if base_url:
        cfg = cfg.model_copy(update={"base_url": base_url})
    return cfg


@account_app.command("register")
def account_register(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """邮箱 + 账户密码 + 私钥备份口令，自动生成密钥并调用服务端注册与 setup-key，保存到本地并设为当前账户。"""
    ensure_client_dirs()
    email = _prompt_email()
    pw1 = getpass.getpass("账户密码（≥8 位，含字母与数字）: ")
    pw2 = getpass.getpass("确认账户密码: ")
    if pw1 != pw2:
        typer.echo("两次密码不一致", err=True)
        raise typer.Exit(1)
    try:
        _validate_password_local(pw1)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    backup_pw = getpass.getpass("私钥备份口令（用于加密上传的私钥备份，换机时需此口令解密）: ")
    if not backup_pw:
        typer.echo("私钥备份口令不能为空", err=True)
        raise typer.Exit(1)

    cfg = _base_cfg(base_url)
    typer.echo(f"MindMemory: {cfg.base_url.rstrip('/')}")

    try:
        post_register(cfg.base_url, email, pw1, timeout_s=cfg.timeout_s)
        typer.echo("注册成功，正在生成密钥并上传公钥…")
    except MindMemoryAPIError as e:
        typer.echo(f"注册失败: {e.detail or e}", err=True)
        raise typer.Exit(1)

    priv, pub = generate_ed25519_openssh_keypair()
    enc_backup = encrypt_private_key_backup_openssh(priv, backup_pw)

    try:
        out = post_setup_key(cfg.base_url, email, pub, enc_backup, timeout_s=cfg.timeout_s)
    except MindMemoryAPIError as e:
        typer.echo(f"上传公钥失败: {e.detail or e}", err=True)
        typer.echo("若邮箱已注册但未完成初始化，请使用「mmem account login」或联系管理员。", err=True)
        raise typer.Exit(1)

    user_uuid = out.get("user_uuid")
    if not user_uuid:
        typer.echo("服务端未返回 user_uuid", err=True)
        raise typer.Exit(1)

    write_private_key_file(str(user_uuid), priv)
    save_account_meta(AccountMeta(email=email, user_uuid=str(user_uuid)))
    st = load_state()
    st.current_account_uuid = str(user_uuid)
    save_state(st)

    typer.echo(f"完成。user_uuid={user_uuid}")
    typer.echo(f"私钥已保存: {account_private_key_path(str(user_uuid))}")
    typer.echo(f"当前账户已切换为此账号。PNMS 数据根: {default_pnms_data_root()}")


@account_app.command("login")
def account_login(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """
    邮箱 + 账户密码登录。

    若本机已有该账户私钥，仅需账户密码；否则需额外输入私钥备份口令以下载并解密云端私钥。
    """
    ensure_client_dirs()
    email = _prompt_email()
    account_pw = getpass.getpass("账户密码: ")
    cfg = _base_cfg(base_url)

    try:
        out = post_login(cfg.base_url, email, account_pw, timeout_s=cfg.timeout_s)
    except MindMemoryAPIError as e:
        typer.echo(f"登录失败: {e.detail or e}", err=True)
        raise typer.Exit(1)

    user_uuid = str(out.get("user_uuid", ""))
    if not user_uuid:
        typer.echo("服务端未返回 user_uuid", err=True)
        raise typer.Exit(1)

    if has_local_private_key(user_uuid):
        try:
            load_ed25519_private_key(account_private_key_path(user_uuid))
        except Exception as e:
            typer.echo(f"本地私钥无效: {e}", err=True)
            raise typer.Exit(1)
        save_account_meta(AccountMeta(email=email, user_uuid=user_uuid))
        st = load_state()
        st.current_account_uuid = user_uuid
        save_state(st)
        typer.echo(f"已登录（使用本机私钥）。当前账户 user_uuid={user_uuid}")
        return

    backup_pw = getpass.getpass(
        "本机尚无该账户私钥，请输入私钥备份口令以下载并解密云端备份: "
    )
    if not backup_pw:
        typer.echo("需要私钥备份口令", err=True)
        raise typer.Exit(1)

    try:
        with MmemApiClient(cfg) as api:
            blob = api.get_encrypted_private_key_backup(user_uuid)
    except MindMemoryAPIError as e:
        typer.echo(f"获取私钥备份失败: {e.detail or e}", err=True)
        raise typer.Exit(1)

    raw = blob.get("encrypted_private_key_backup")
    if not raw:
        typer.echo("服务端未返回 encrypted_private_key_backup", err=True)
        raise typer.Exit(1)

    try:
        priv = decrypt_private_key_backup_openssh(str(raw), backup_pw)
    except Exception as e:
        typer.echo(f"解密私钥失败（口令错误或备份损坏）: {e}", err=True)
        raise typer.Exit(1)

    try:
        # 写入临时路径再加载校验
        write_private_key_file(user_uuid, priv)
        load_ed25519_private_key(account_private_key_path(user_uuid))
    except Exception as e:
        typer.echo(f"私钥格式校验失败: {e}", err=True)
        raise typer.Exit(1)

    save_account_meta(AccountMeta(email=email, user_uuid=user_uuid))
    st = load_state()
    st.current_account_uuid = user_uuid
    save_state(st)
    typer.echo(f"已登录并恢复私钥。user_uuid={user_uuid}")


@account_app.command("logout")
def account_logout() -> None:
    """清除当前会话（不删除本地账户目录与私钥）。"""
    st = load_state()
    if not st.current_account_uuid:
        typer.echo("当前未选择任何账户。")
        return
    uid = st.current_account_uuid
    st.current_account_uuid = None
    save_state(st)
    typer.echo(f"已登出（此前当前账户为 {uid}）。")


@account_app.command("list")
def account_list() -> None:
    """列出本机已保存的账户。"""
    rows = list_local_accounts()
    st = load_state()
    cur = st.current_account_uuid
    if not rows:
        typer.echo("本机尚无已保存账户（可先 mmem account register / login）。")
        return
    for m in rows:
        mark = " *" if m.user_uuid == cur else ""
        typer.echo(f"{m.email}\t{m.user_uuid}{mark}")


@account_app.command("use")
def account_use(
    identifier: str = typer.Argument(..., help="user_uuid 或邮箱"),
) -> None:
    """将当前会话切换为已存在于本机的账户。"""
    s = identifier.strip()
    meta: AccountMeta | None = None
    if "@" in s:
        meta = find_account_by_email(s)
    else:
        for m in list_local_accounts():
            if m.user_uuid == s:
                meta = m
                break
    if not meta:
        typer.echo("未找到匹配的本地账户。", err=True)
        raise typer.Exit(1)
    if not has_local_private_key(meta.user_uuid):
        typer.echo("该账户本地无私钥文件，请先 mmem account login。", err=True)
        raise typer.Exit(1)

    st = load_state()
    st.current_account_uuid = meta.user_uuid
    save_state(st)
    typer.echo(f"当前账户: {meta.email} ({meta.user_uuid})")


@account_app.command("whoami")
def account_whoami(
    base_url: Optional[str] = typer.Option(None, envvar="MMEM_BASE_URL"),
) -> None:
    """显示当前解析的配置与 GET /me（需已登录且可访问服务端）。"""
    cfg = resolve_mmem_config(base_url_override=base_url)
    typer.echo(f"MMEM_CREDENTIAL_SOURCE: {credential_source()}")
    typer.echo(f"配置目录: {client_config_dir()}")
    typer.echo(f"数据目录: {client_data_dir()}")
    typer.echo(f"MMEM_BASE_URL: {cfg.base_url.rstrip('/')}")
    if cfg.user_uuid:
        typer.echo(f"user_uuid: {cfg.user_uuid}")
    else:
        typer.echo("user_uuid: （未设置）")
    if cfg.private_key_path:
        typer.echo(f"private_key: {cfg.private_key_path}")
    else:
        typer.echo("private_key: （未设置）")
    typer.echo(f"pnms_data_root: {cfg.pnms_data_root}")

    if not cfg.user_uuid:
        typer.echo("未配置用户，跳过 /me。")
        return

    try:
        with MmemApiClient(cfg) as api:
            me = api.get_me(cfg.user_uuid)
            typer.echo(f"GET /me: {me}")
    except MindMemoryAPIError as e:
        typer.echo(f"GET /me 失败: {e.detail or e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"GET /me 失败: {e}", err=True)
        raise typer.Exit(1)
