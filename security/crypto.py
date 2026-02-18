import os
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class CryptoHelper:
    """Derives an AES‑256‑GCM key from a passphrase."""
    LEGACY_SALT = b'\x12\x34\x56\x78\x9a\xbc\xde\xf0'
    def __init__(self, passphrase: str):
        # Keep stable across runs so stored SMTP credentials remain decryptable.
        self._salt_path = os.environ.get(
            "CROSSMAILER_SALT_PATH",
            os.path.join(os.path.dirname(__file__), "..", "data", "crypto_salt.bin"),
        )
        self._salt = self._load_or_init_salt()
        self.key = self._derive_key(passphrase, self._salt)

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        kdf_inst = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=200_000,
        )
        return kdf_inst.derive(passphrase.encode())

    def _load_or_init_salt(self) -> bytes:
        salt_path = os.path.abspath(self._salt_path)
        os.makedirs(os.path.dirname(salt_path), exist_ok=True)

        if os.path.exists(salt_path):
            with open(salt_path, "rb") as f:
                data = f.read()
            if len(data) >= 16:
                return data[:16]

        # Backwards compatibility:
        # If an existing SMTP DB is present, stick to the legacy salt so old
        # encrypted passwords remain decryptable.
        smtp_db = os.path.join(os.path.dirname(__file__), "..", "data", "smtp_credentials.db")
        if os.path.exists(smtp_db):
            # Persist legacy salt so future runs behave consistently.
            with open(salt_path, "wb") as f:
                f.write(self.LEGACY_SALT)
            return self.LEGACY_SALT

        salt = os.urandom(16)
        with open(salt_path, "wb") as f:
            f.write(salt)
        return salt

def encrypt(plaintext: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ct)

def decrypt(token: str, key: bytes) -> bytes:
    data = base64.b64decode(token)
    nonce, ct = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)
