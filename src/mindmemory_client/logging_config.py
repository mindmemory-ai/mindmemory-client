"""客户端日志：由 ``MMEM_LOG_*`` 环境变量控制（经 ``.env`` 或 shell）。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from mindmemory_client.env_loader import get_env

_CONFIGURED = False

_LEVEL_NAMES = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

# 与 CLI 相关的顶层 logger 名（子 logger 如 mindmemory_client.api 会向上冒泡）
_ROOT_LOGGERS = ("mindmemory_client", "mmem_cli")


def _parse_level(raw: str | None) -> int:
    if not raw or not raw.strip():
        return logging.INFO
    return _LEVEL_NAMES.get(raw.strip().upper(), logging.INFO)


def configure_client_logging() -> None:
    """
    为 ``mindmemory_client`` / ``mmem_cli`` 配置处理器与级别。

    幂等：同一进程仅初始化一次。应在 ``mmem`` CLI 入口尽早调用（在读取 ``.env`` 之后通过 ``get_env`` 生效）。
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = _parse_level(get_env("MMEM_LOG_LEVEL"))
    fmt_raw = get_env("MMEM_LOG_FORMAT")
    fmt = fmt_raw or "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)

    handlers: list[logging.Handler] = [stream]
    log_path = get_env("MMEM_LOG_FILE")
    if log_path and log_path.strip():
        p = Path(log_path).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(p, encoding="utf-8")
            fh.setFormatter(formatter)
            handlers.append(fh)
        except OSError as e:
            sys.stderr.write(f"[mmem] 无法打开 MMEM_LOG_FILE={p}: {e}\n")

    for name in _ROOT_LOGGERS:
        log = logging.getLogger(name)
        log.handlers.clear()
        for h in handlers:
            log.addHandler(h)
        log.setLevel(level)
        log.propagate = False

    _CONFIGURED = True


def reset_client_logging_for_tests() -> None:
    """测试用：清除幂等标志与处理器。"""
    global _CONFIGURED
    _CONFIGURED = False
    for name in _ROOT_LOGGERS:
        log = logging.getLogger(name)
        log.handlers.clear()
        log.setLevel(logging.NOTSET)
        log.propagate = True
