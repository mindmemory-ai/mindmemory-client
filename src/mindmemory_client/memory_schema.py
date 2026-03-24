"""memory_schema_version（Git 分支名与提交元数据）与 PNMS 记忆文件格式版本对齐。"""

from __future__ import annotations


def resolve_memory_schema_version(cli_schema: str | None) -> str:
    """
    解析最终 ``memory_schema_version`` / Git 分支名 ``refs/heads/<version>``。

    - 若命令行传入 ``--schema``，使用该值；
    - 否则使用 PNMS ``get_memory_format_version()``；
    - 未安装 pnms 时回退 ``"1.0.0"``。
    """
    if cli_schema is not None and str(cli_schema).strip():
        return str(cli_schema).strip()
    try:
        from pnms import get_memory_format_version

        return get_memory_format_version()
    except ImportError:
        return "1.0.0"
