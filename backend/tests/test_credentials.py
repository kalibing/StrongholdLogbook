from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from logbook import storage
from logbook.api import app
from logbook.credentials import ACHIEVEMENTS, PREFIX, SKLAND, CredentialStorageError, CredentialVault


def test_ciphertext_belongs_to_one_account_and_purpose():
    vault = CredentialVault(b"\x00" * 32)
    owner = uuid4()
    ciphertext = vault.seal(SKLAND, owner, "example-token")
    assert vault.unseal(SKLAND, owner, ciphertext) == "example-token"
    assert vault.seal(SKLAND, owner, "example-token") != ciphertext
    with pytest.raises(CredentialStorageError):
        vault.unseal(SKLAND, uuid4(), ciphertext)
    with pytest.raises(CredentialStorageError):
        vault.unseal(ACHIEVEMENTS, owner, ciphertext)
    with pytest.raises(CredentialStorageError):
        CredentialVault(b"\x01" * 32).unseal(SKLAND, owner, ciphertext)


def test_startup_encrypts_legacy_tokens_and_can_reuse_the_local_key(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGBOOK_CREDENTIAL_KEY", raising=False)
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    db_path = tmp_path / "archive.sqlite3"
    monkeypatch.setenv("LOGBOOK_SQLITE", str(db_path))
    owner = uuid4()
    with storage.connect() as database:
        database.execute("INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                         (owner, "legacy-user", "test-hash"))
        database.execute("INSERT INTO skland_import_tokens (user_id, access_token) VALUES (%s, %s)",
                         (owner, "legacy-import-token"))
        database.execute("""
            INSERT INTO achv_links (user_id, source, u8_token, payload, fetched_at, updated_at)
            VALUES (%s, 'token', %s, %s, now(), now())
        """, (owner, "legacy-achievement-token", storage.json_param({"likes": 3})))

    with TestClient(app):
        with storage.connect() as database:
            skland = database.execute("SELECT access_token FROM skland_import_tokens").fetchone()["access_token"]
            achievement = database.execute("SELECT u8_token, payload FROM achv_links").fetchone()

    assert skland.startswith(PREFIX) and "legacy-import-token" not in skland
    assert achievement["u8_token"].startswith(PREFIX) and "legacy-achievement-token" not in achievement["u8_token"]
    assert achievement["payload"] == {"likes": 3}

    with TestClient(app):
        assert app.state.credentials.unseal(SKLAND, owner, skland) == "legacy-import-token"
        assert app.state.credentials.unseal(ACHIEVEMENTS, owner, achievement["u8_token"]) == "legacy-achievement-token"

    db_path.with_name(db_path.name + ".credentials.key").unlink()
    with pytest.raises(CredentialStorageError, match="找不到 SQLite 的凭据密钥"):
        with TestClient(app):
            pytest.fail("An encrypted database cannot be opened by a replacement key")
