import os
from dataclasses import dataclass
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def validate_origin(value: str) -> str:
    """只接受 HTTPS 源，或本机回环上的 HTTP 源；返回去掉末尾斜杠的规范形式。"""
    origin = urlsplit(value)
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
        or (origin.scheme == "http" and origin.hostname not in LOOPBACK_HOSTS)
    ):
        raise ValueError("PUBLIC_ORIGIN must be an HTTPS origin, or HTTP on a loopback host")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    public_origin: str

    @property
    def cookie_secure(self) -> bool:
        return self.public_origin.startswith("https://")

    @property
    def database_url(self) -> dict:
        return {
            "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "username": os.getenv("POSTGRES_USER", "logbook"),
            "database": os.getenv("POSTGRES_DB", "logbook"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
        }

    @property
    def connect_kwargs(self) -> dict:
        values = self.database_url
        values["user"] = values.pop("username")
        values["dbname"] = values.pop("database")
        return values


settings = Settings(validate_origin(os.getenv("PUBLIC_ORIGIN", "http://localhost:8080")))
