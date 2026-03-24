"""记忆子系统异常：封装底层引擎错误，不向上暴露 pnms 类型。"""

from __future__ import annotations

from typing import Any


class MemoryEngineError(Exception):
    """记忆引擎（PNMS）操作失败；``code`` 与底层稳定错误码对齐，便于分支处理。"""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.cause = cause

    def __str__(self) -> str:
        base = super().__str__()
        if self.code:
            return f"[{self.code}] {base}"
        return base


def wrap_engine_exception(exc: BaseException) -> BaseException:
    """若为底层 PNMSError，包装为 ``MemoryEngineError``；否则原样返回。"""
    if isinstance(exc, MemoryEngineError):
        return exc
    try:
        from pnms import PNMSError

        if isinstance(exc, PNMSError):
            return MemoryEngineError(
                str(exc),
                code=getattr(exc, "code", None),
                cause=exc,
            )
    except ImportError:
        pass
    return exc
