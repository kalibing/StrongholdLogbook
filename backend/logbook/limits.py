"""进程内的请求防护：请求体总量上限、按来源 IP 的登录失败限速。

两者都不依赖数据库，单进程内生效；多 API 进程时每个进程各自计数，上限按进程数放大，
仍远低于暴力破解所需的量级。账号级锁定（连续 8 次失败锁 15 分钟）在数据库里，跨进程生效。
"""

from collections import deque
from ipaddress import ip_address, ip_network
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

    def __init__(self, limit: int = 5, window: float = 60 * 60, max_keys: int = 10_000):
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

    # 用作一般的频率计数（注册次数、接口调用次数）时的别名。
    hit = failed

    def take(self, key: str) -> bool:
        """原子地「检查 + 记一次」：未超限时计数并返回 True，超限返回 False 且不计数。"""
        with self._lock:
            failures = self._prune(key, time.monotonic())
            if failures is not None and len(failures) >= self.limit:
                return False
        self.failed(key)
        return True

    def refund(self, key: str) -> None:
        """撤销最近一次计数（调用没有成功时不占用额度）。"""
        with self._lock:
            failures = self._failures.get(key)
            if failures:
                failures.pop()
                if not failures:
                    del self._failures[key]

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def client_key(request) -> str:
    """限速用的来源标识。IPv6 按 /64 网段归并：一台主机通常能随意换用整个 /64 里的地址。"""
    host = request.client.host if request.client else ""
    try:
        address = ip_address(host)
    except ValueError:
        return host or "unknown"
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ip_network(f"{address}/64", strict=False))
    return str(address)
