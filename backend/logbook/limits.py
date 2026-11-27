"""进程内的请求防护：请求体总量上限、按来源 IP 的登录失败限速。

两者都不依赖数据库，单进程内生效；多 API 进程时每个进程各自计数，上限按进程数放大，
仍远低于暴力破解所需的量级。账号级锁定（连续 8 次失败锁 15 分钟）在数据库里，跨进程生效。
"""

from collections import deque
from threading import Lock
import time

from starlette.responses import JSONResponse

# 比单个接口的上限（导入 8 MB、头像 2 MB）略宽，兜住所有用 Pydantic 读全量请求体的接口。
MAX_REQUEST_BYTES = 9 * 1024 * 1024


class BodyTooLarge(Exception):
    pass


class RequestSizeLimit:
    """纯 ASGI 中间件：Content-Length 超限直接 413；分块上传按实际读到的字节数截断。"""

    def __init__(self, app, limit: int = MAX_REQUEST_BYTES):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                if not value.isdigit() or int(value) > self.limit:
                    return await self.reject(scope, receive, send)
                break

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if not started:
                await self.reject(scope, receive, send)

    @staticmethod
    async def reject(scope, receive, send):
        response = JSONResponse({"detail": "请求体过大"}, 413, headers={"Cache-Control": "no-store"})
        await response(scope, receive, send)


class FailureThrottle:
    """滑动窗口：同一来源在 window 秒内失败超过 limit 次即拒绝，直到最早的失败滑出窗口。"""

    def __init__(self, limit: int = 20, window: float = 15 * 60, max_keys: int = 10_000):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._failures: dict[str, deque] = {}
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque | None:
        failures = self._failures.get(key)
        if failures is None:
            return None
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures

    def blocked(self, key: str) -> bool:
        with self._lock:
            failures = self._prune(key, time.monotonic())
            return failures is not None and len(failures) >= self.limit

    def failed(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if key not in self._failures and len(self._failures) >= self.max_keys:
                for stale in list(self._failures):
                    self._prune(stale, now)
                if len(self._failures) >= self.max_keys:
                    # 表满时丢掉最早的来源，内存有界；被挤掉的来源最多多试一个窗口的量。
                    self._failures.pop(next(iter(self._failures)))
            self._failures.setdefault(key, deque()).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
