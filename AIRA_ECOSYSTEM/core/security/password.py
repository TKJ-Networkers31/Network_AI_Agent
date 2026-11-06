"""
AIRA OS — Secure Password Hashing & Verification (Workstream A / OWASP ASVS 5.0).

Features:
- Primary: Argon2id (OWASP ASVS 5.0 recommended password storage algorithm)
  time_cost=2, memory_cost=65536 (64 MiB), parallelism=1, hash_len=32.
- Backward-compatibility: Verifies legacy PBKDF2-HMAC-SHA256 hashes and flags
  them for transparent upgrade to Argon2id upon successful authentication.
- Constant-time comparison to prevent timing side-channel attacks.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Optional, Tuple

logger = logging.getLogger("aira.security.password")

try:
    import argon2
    from argon2.exceptions import InvalidHash, VerifyMismatchError, VerificationError
    _ARGON2_AVAILABLE = True
    _argon2_hasher = argon2.PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=1,
        hash_len=32,
        type=argon2.Type.ID,
    )
except ImportError:
    _ARGON2_AVAILABLE = False
    _argon2_hasher = None
    logger.warning("argon2-cffi not installed; falling back to PBKDF2-HMAC-SHA256")


def hash_password(password: str) -> str:
    """
    Hashes a password using Argon2id (or PBKDF2 fallback if library unavailable).
    Returns an Argon2id formatted hash string ($argon2id$v=19$...).
    """
    if not password:
        raise ValueError("Password cannot be empty.")

    if _ARGON2_AVAILABLE and _argon2_hasher is not None:
        return _argon2_hasher.hash(password)

    # Fallback to PBKDF2-HMAC-SHA256 with 100,000 rounds
    salt = secrets.token_hex(16)
    raw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return f"$pbkdf2-sha256$100000${salt}${raw_hash}"


def _verify_pbkdf2(password: str, stored_hash: str, salt: Optional[str] = None) -> bool:
    """Verifies a legacy PBKDF2 hash against a password."""
    if stored_hash.startswith("$pbkdf2-sha256$"):
        parts = stored_hash.split("$")
        if len(parts) >= 5:
            iterations = int(parts[2])
            salt_val = parts[3]
            expected = parts[4]
            computed = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt_val.encode("utf-8"),
                iterations,
            ).hex()
            return secrets.compare_digest(computed, expected)
    elif salt:
        # Phase G legacy format: raw hex with salt stored in separate column
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        ).hex()
        return secrets.compare_digest(computed, stored_hash)

    return False


def verify_password(
    password: str,
    stored_hash: str,
    salt: Optional[str] = None,
) -> Tuple[bool, bool]:
    """
    Verifies a plaintext password against the stored hash.

    Returns:
        (is_valid, needs_rehash):
        - is_valid: True if password matches, False otherwise.
        - needs_rehash: True if the hash is legacy (PBKDF2) or Argon2 parameters need upgrade,
          prompting the caller to update the user's stored hash to modern Argon2id.
    """
    if not password or not stored_hash:
        return False, False

    # Case 1: Argon2id hash format
    if stored_hash.startswith("$argon2"):
        if not _ARGON2_AVAILABLE or _argon2_hasher is None:
            logger.error("Stored password is Argon2id but argon2 library is not available.")
            return False, False
        try:
            _argon2_hasher.verify(stored_hash, password)
            needs_rehash = _argon2_hasher.check_needs_rehash(stored_hash)
            return True, needs_rehash
        except (VerifyMismatchError, VerificationError, InvalidHash):
            return False, False

    # Case 2: Legacy PBKDF2 hash
    is_valid = _verify_pbkdf2(password, stored_hash, salt)
    if is_valid:
        # Needs rehash to modern Argon2id!
        return True, True

    return False, False
