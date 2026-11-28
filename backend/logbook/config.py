import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
BACKENDS = {
    "postgres": "postgres", "postgresql": "postgres", "psycopg": "postgres",
    "sqlite": "sqlite", "sqlite3": "sqlite",
}


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
    def backend(self) -> str:
        """LOGBOOK_DB=postgres（默认）| sqlite。"""
        value = os.getenv("LOGBOOK_DB", "postgres").strip().lower()
        try:
            return BACKENDS[value]
        except KeyError:
            raise ValueError("LOGBOOK_DB must be 'postgres' or 'sqlite'") from None

    @property
    def registration(self) -> str:
        """LOGBOOK_REGISTRATION=off（默认，只能用命令行建号）| open（网页开放注册）。"""
        value = os.getenv("LOGBOOK_REGISTRATION", "off").strip().lower() or "off"
        if value not in {"off", "open"}:
            raise ValueError("LOGBOOK_REGISTRATION must be 'off' or 'open'")
        return value

    @property
    def qq_app_id(self) -> str:
        return os.getenv("QQBOT_APP_ID", "").strip()

    @property
    def qq_bind_command(self) -> str:
        return self._qq_command("QQBOT_BIND_COMMAND", "绑定")

    @property
    def qq_report_command(self) -> str:
        return self._qq_command("QQBOT_REPORT_COMMAND", "日报")

    @property
    def qq_record_command(self) -> str:
        return self._qq_command("QQBOT_RECORD_COMMAND", "战绩")

    @property
    def qq_winrate_command(self) -> str:
        return self._qq_command("QQBOT_WINRATE_COMMAND", "胜率")

    @staticmethod
    def _qq_command(variable: str, default: str) -> str:
        value = os.getenv(variable, "").strip() or default
        if not re.fullmatch(r"[\w-]{1,16}", value):
            raise ValueError(f"{variable} must be a single command of 1–16 characters")
        return value

    @property
    def sqlite_path(self) -> Path:
        return Path(os.getenv("LOGBOOK_SQLITE", "logbook.sqlite3")).expanduser()

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
