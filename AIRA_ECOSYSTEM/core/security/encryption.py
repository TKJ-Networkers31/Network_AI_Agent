"""
AIRA OS — Centralized Secret Encryption Vault (Stage 3 / OWASP ASVS 5.0).
Provides authenticated AES-256-GCM encryption for all secrets at rest:
- Router SSH passwords and private keys
- LLM Provider API keys
- Multi-factor authentication (TOTP) seed secrets

Features:
- Primary Cipher: AES-256-GCM (NIST SP 800-38D compliant with 96-bit cryptographically fresh nonce)
- Master Key Management:
  1. Priority 1: AIRA_MASTER_KEY environment variable (Base64-encoded 32 bytes or passphrase)
  2. Priority 2: File-backed key in database/.master.key (auto-generated with POSIX 0600 permissions)
- Key Rotation: Safe re-encryption of ciphertexts under a new master key
- Transparent Backward Compatibility: Decrypts legacy Fernet (enc:...) and base64 (b64:...) payloads
- Tamper Detection: Authenticated Galois/Counter Mode authentication tag verification
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple, Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("aira.security.encryption")

DEFAULT_KEY_FILE = Path(__file__).resolve().parent.parent.parent / "database" / ".master.key"
MAGIC_PREFIX = "aira_enc_v1$"


class VaultError(Exception):
    """Base exception for SecretVault errors."""
    pass


class VaultDecryptionError(VaultError):
    """Raised when ciphertext cannot be decrypted or authentication tag verification fails."""
    pass


class SecretVault:
    """
    Enterprise AES-256-GCM Secret Encryption Vault.
    Guarantees confidentiality and integrity for sensitive data at rest.
    """

    def __init__(
        self,
        master_key: Optional[Union[str, bytes]] = None,
        key_file_path: Optional[Path] = None,
    ) -> None:
        self._key_file = key_file_path or DEFAULT_KEY_FILE
        self._raw_key: bytes = self._resolve_master_key(master_key)
        self._aesgcm = AESGCM(self._raw_key)

    def _resolve_master_key(self, explicit_key: Optional[Union[str, bytes]]) -> bytes:
        """Resolves 32-byte AES-256 key from explicit param, environment, or secure keyfile."""
        if explicit_key:
            return self._derive_32byte_key(explicit_key)

        env_key = os.getenv("AIRA_MASTER_KEY", "").strip() or os.getenv("AIRA_SECRET_KEY", "").strip()
        if env_key:
            return self._derive_32byte_key(env_key)

        # File-backed master key
        if self._key_file.exists():
            try:
                raw_bytes = self._key_file.read_bytes().strip()
                if raw_bytes:
                    return self._derive_32byte_key(raw_bytes)
            except Exception as e:
                logger.warning("Failed to read master key from %s: %s", self._key_file, e)

        # Generate fresh 256-bit key
        new_key = AESGCM.generate_key(bit_length=256)
        try:
            self._key_file.parent.mkdir(parents=True, exist_ok=True)
            self._key_file.write_bytes(base64.b64encode(new_key))
            if os.name != "nt":
                os.chmod(self._key_file, 0o600)
            logger.info("Generated new master encryption key at %s (keep secure, never commit)", self._key_file)
        except Exception as e:
            logger.warning("Could not persist master key file at %s: %s", self._key_file, e)

        return new_key

    @staticmethod
    def _derive_32byte_key(key_input: Union[str, bytes]) -> bytes:
        """Derives exactly 32 bytes from raw key input or passphrase."""
        if isinstance(key_input, str):
            key_bytes = key_input.encode("utf-8")
        else:
            key_bytes = key_input

        # Try base64 decoding in case of 32-byte base64 string
        try:
            decoded = base64.b64decode(key_bytes)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass

        # If exactly 32 bytes
        if len(key_bytes) == 32:
            return key_bytes

        # Derive 32 bytes using SHA-256
        return hashlib.sha256(key_bytes).digest()

    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        """
        Encrypts plaintext string with AES-256-GCM.
        Returns: 'aira_enc_v1$<nonce_b64>$<ciphertext_and_tag_b64>'
        Idempotent: if already encrypted with MAGIC_PREFIX, returns unchanged.
        """
        if plaintext is None:
            return None

        clean_text = str(plaintext)
        if clean_text.startswith(MAGIC_PREFIX):
            return clean_text

        nonce = os.urandom(12)  # 96-bit standard GCM nonce
        data = clean_text.encode("utf-8")
        ciphertext = self._aesgcm.encrypt(nonce, data, None)

        nonce_b64 = base64.urlsafe_b64encode(nonce).decode("ascii")
        ct_b64 = base64.urlsafe_b64encode(ciphertext).decode("ascii")

        return f"{MAGIC_PREFIX}{nonce_b64}${ct_b64}"

    def decrypt(self, ciphertext: Optional[str]) -> Optional[str]:
        """
        Decrypts ciphertext string.
        Supports:
        - aira_enc_v1$<nonce>$<ciphertext> (AES-256-GCM)
        - enc:<fernet> (legacy Fernet migration)
        - b64:<data> (legacy base64 fallback)
        - Raw plaintext (returned as-is)
        """
        if ciphertext is None:
            return None

        val = str(ciphertext).strip()

        # 1. Primary: AES-256-GCM
        if val.startswith(MAGIC_PREFIX):
            parts = val.split("$")
            if len(parts) != 3:
                raise VaultDecryptionError("Malformed ciphertext structure.")

            try:
                nonce = base64.urlsafe_b64decode(parts[1])
                ct = base64.urlsafe_b64decode(parts[2])
                decrypted = self._aesgcm.decrypt(nonce, ct, None)
                return decrypted.decode("utf-8")
            except Exception as e:
                raise VaultDecryptionError(f"Decryption or authentication failed: {e}") from e

        # 2. Legacy: Fernet (enc:...)
        if val.startswith("enc:"):
            try:
                from cryptography.fernet import Fernet
                # Try with derived fernet key
                f_key = base64.urlsafe_b64encode(self._raw_key)
                f = Fernet(f_key)
                return f.decrypt(val[4:].encode("ascii")).decode("utf-8")
            except Exception:
                # Try fallback legacy inventory key file if exists
                try:
                    legacy_key_file = self._key_file.parent / ".inventory.key"
                    if legacy_key_file.exists():
                        f = Fernet(legacy_key_file.read_bytes().strip())
                        return f.decrypt(val[4:].encode("ascii")).decode("utf-8")
                except Exception as ex:
                    raise VaultDecryptionError(f"Failed to decrypt legacy Fernet secret: {ex}") from ex
                raise VaultDecryptionError("Failed to decrypt legacy Fernet secret with master key.")

        # 3. Legacy: Base64 (b64:...)
        if val.startswith("b64:"):
            try:
                return base64.b64decode(val[4:]).decode("utf-8")
            except Exception as e:
                raise VaultDecryptionError(f"Failed to decode legacy base64 secret: {e}") from e

        # Raw string / unencrypted plaintext
        return val

    def rotate_key(
        self,
        new_master_key: Union[str, bytes],
        ciphertext: str,
    ) -> str:
        """
        Re-encrypts a ciphertext under a new master key.
        """
        plaintext = self.decrypt(ciphertext)
        new_vault = SecretVault(master_key=new_master_key, key_file_path=self._key_file)
        return new_vault.encrypt(plaintext) or ""


# -----------------------------------------------------------------------------
# Global Singleton & Helper Facade
# -----------------------------------------------------------------------------

_vault_lock = threading.Lock()
_global_vault: Optional[SecretVault] = None


def get_secret_vault() -> SecretVault:
    """Returns the process-wide SecretVault singleton."""
    global _global_vault
    if _global_vault is not None:
        return _global_vault
    with _vault_lock:
        if _global_vault is None:
            _global_vault = SecretVault()
        return _global_vault


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Helper to encrypt a secret using the global vault."""
    return get_secret_vault().encrypt(plaintext)


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Helper to decrypt a secret using the global vault."""
    return get_secret_vault().decrypt(ciphertext)
