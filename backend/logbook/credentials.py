"""Encrypt stored credentials and authenticate their owner and purpose."""

import base64
import os
from tempfile import NamedTemporaryFile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings

PREFIX = "logbook:aesgcm:v1:"
SKLAND = "skland-import"
ACHIEVEMENTS = "achievements"
STORES = (
    ("skland_import_tokens", "access_token", SKLAND),
    ("achv_links", "u8_token", ACHIEVEMENTS),
)


class CredentialStorageError(Exception):
    pass


class CredentialVault:
    def __init__(self, key):
        self._cipher = AESGCM(key)

    def seal(self, purpose, user_id, token):
        nonce = os.urandom(12)
        sealed = self._cipher.encrypt(nonce, token.encode(), f"{purpose}:{user_id}".encode())
        return PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")

    def unseal(self, purpose, user_id, value):
        try:
            if not value.startswith(PREFIX):
                raise ValueError("Missing credential format marker")
            sealed = base64.b64decode(value[len(PREFIX):], altchars=b"-_", validate=True)
            return self._cipher.decrypt(sealed[:12], sealed[12:], f"{purpose}:{user_id}".encode()).decode()
        except (ValueError, InvalidTag) as error:
            raise CredentialStorageError("无法读取已保存的凭据") from error


def load_key(has_encrypted_credentials):
    configured = os.getenv("LOGBOOK_CREDENTIAL_KEY", "").strip()
    if not configured:
        if settings.backend != "sqlite":
            raise CredentialStorageError("请设置 LOGBOOK_CREDENTIAL_KEY")
        path = settings.sqlite_path.with_name(settings.sqlite_path.name + ".credentials.key")
        if path.is_file():
            configured = path.read_text(encoding="ascii").strip()
        elif has_encrypted_credentials:
            raise CredentialStorageError("找不到 SQLite 的凭据密钥，请恢复密钥文件或设置 LOGBOOK_CREDENTIAL_KEY")
        else:
            key = AESGCM.generate_key(bit_length=256)
            # The SQLite startup transaction serializes creation across API processes.
            with NamedTemporaryFile(dir=path.parent, delete=False) as file:
                file.write(base64.urlsafe_b64encode(key))
            try:
                os.replace(file.name, path)
            finally:
                if os.path.exists(file.name):
                    os.unlink(file.name)
            return key
    try:
        key = base64.b64decode(configured, altchars=b"-_", validate=True)
    except ValueError as error:
        raise CredentialStorageError("LOGBOOK_CREDENTIAL_KEY 必须是 URL-safe Base64 编码的 32 字节密钥") from error
    if len(key) != 32:
        raise CredentialStorageError("LOGBOOK_CREDENTIAL_KEY 必须是 URL-safe Base64 编码的 32 字节密钥")
    return key


def initialize_vault(database):
    """Convert legacy plaintext rows in the startup transaction, leaving cached data intact."""
    stores = [
        (table, column, purpose, database.execute(f"SELECT user_id, {column} FROM {table} FOR UPDATE").fetchall())
        for table, column, purpose in STORES
    ]
    vault = CredentialVault(load_key(
        any(row[column].startswith(PREFIX) for _, column, _, rows in stores for row in rows)
    ))
    for table, column, purpose, rows in stores:
        for row in rows:
            user_id, value = row["user_id"], row[column]
            if value.startswith(PREFIX):
                vault.unseal(purpose, user_id, value)
            else:
                database.execute(
                    f"UPDATE {table} SET {column} = %s WHERE user_id = %s",
                    (vault.seal(purpose, user_id, value), user_id),
                )
    return vault
