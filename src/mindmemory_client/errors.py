class MindMemoryAPIError(Exception):
    """MindMemory HTTP API 返回非 2xx 或响应体无法解析。"""

    def __init__(self, message: str, status_code: int | None = None, detail: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
