import pytest

from logbook.config import Settings, validate_origin


@pytest.mark.parametrize("value", [
    "https://logbook.example.com",
    "https://logbook.example.com/",
    "http://localhost:8080",
    "http://127.0.0.1:8000",
    "http://[::1]:8080",
])
def test_valid_origins(value):
    assert validate_origin(value) == value.rstrip("/")


@pytest.mark.parametrize("value", [
    "",
    "logbook.example.com",
    "ftp://logbook.example.com",
    "http://logbook.example.com",
    "https://logbook.example.com/app",
    "https://logbook.example.com?next=/x",
    "https://logbook.example.com#top",
    "https://user:secret@logbook.example.com",
])
def test_invalid_origins(value):
    with pytest.raises(ValueError):
        validate_origin(value)


def test_cookie_secure_follows_scheme():
    assert Settings("https://logbook.example.com").cookie_secure is True
    assert Settings("http://localhost:8080").cookie_secure is False


def test_database_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "logbook")
    monkeypatch.setenv("POSTGRES_DB", "records")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    settings = Settings("https://logbook.example.com")
    assert settings.connect_kwargs == {
        "host": "db", "port": 5433, "user": "logbook", "dbname": "records", "password": "secret",
    }
    url = settings.database_url
    assert url["username"] == "logbook"
    assert url["database"] == "records"
