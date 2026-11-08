"""
AIRA OS — Multi-Factor Authentication (MFA / TOTP) Engine.
Implements RFC 6238 Time-Based One-Time Password algorithm.
Fully compatible with Google Authenticator, Authy, and standard authenticator apps.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from typing import Tuple


def generate_totp_secret(length: int = 20) -> str:
    """Generates a cryptographically random Base32 TOTP secret."""
    raw = os.urandom(length)
    return base64.b32encode(raw).decode("utf-8").replace("=", "")


def _get_time_counter(time_step: int = 30, for_time: float | None = None) -> int:
    current_time = time.time() if for_time is None else for_time
    return int(current_time // time_step)


def compute_totp_code(secret: str, time_step: int = 30, for_time: float | None = None, digits: int = 6) -> str:
    """Computes standard 6-digit TOTP code for the given secret at current or specified time."""
    # Pad base32 secret if needed
    cleaned_secret = secret.strip().upper()
    missing_padding = len(cleaned_secret) % 8
    if missing_padding:
        cleaned_secret += "=" * (8 - missing_padding)

    key = base64.b32decode(cleaned_secret, casefold=True)
    counter = _get_time_counter(time_step, for_time)
    counter_bytes = struct.pack(">Q", counter)

    hmac_digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = hmac_digest[-1] & 0x0F
    code_int = struct.unpack(">I", hmac_digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = code_int % (10**digits)
    return str(code).zfill(digits)


def verify_totp_code(secret: str, code: str, window: int = 1, time_step: int = 30) -> bool:
    """
    Verifies a user-provided 6-digit TOTP code with time drift window.
    Window=1 allows codes from +/- 30 seconds to tolerate slight clock differences.
    """
    if not secret or not code:
        return False

    code_str = str(code).strip()
    if len(code_str) != 6 or not code_str.isdigit():
        return False

    now = time.time()
    for step_offset in range(-window, window + 1):
        test_time = now + (step_offset * time_step)
        expected = compute_totp_code(secret, time_step=time_step, for_time=test_time)
        if hmac.compare_digest(expected, code_str):
            return True
    return False


def get_totp_uri(secret: str, username: str, issuer: str = "AIRA OS") -> str:
    """Generates standard otpauth:// URI for authenticator QR code generation."""
    clean_secret = secret.strip().upper()
    return f"otpauth://totp/{issuer}:{username}?secret={clean_secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
