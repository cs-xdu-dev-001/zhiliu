import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretDecryptionError(Exception):
    pass


class SecretCipher:
    def __init__(self, secret_key: str) -> None:
        if len(secret_key) < 32:
            raise ValueError("集成密钥长度必须至少32字符")
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretDecryptionError("Hermes密钥无法解密，请重新配置") from exc
