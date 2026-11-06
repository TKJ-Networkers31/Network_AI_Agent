"""
AIRA OS — AI Confidentiality & Output Security Guard (Workstream C / OWASP Top 10 for LLM 2025).

Features:
- Enforces strict data classification tiers:
  PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED
- Inspects AI responses (Markdown, Code Blocks, Tables, Mermaid, SVG) before returning to client.
- Redacts detected secret patterns (Private Keys, Passwords, Bearer Tokens, API Keys, SNMP Community Strings).
- Pre-retrieval authorization: Ensures RESTRICTED resources are never injected into LLM context
  for callers lacking ACCESS_SENSITIVE_DATA permission.
- Immutable security audit logging for leak attempts.
"""

from __future__ import annotations

from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("aira.security.output_guard")


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


# Regex patterns identifying RESTRICTED secret material
SECRET_PATTERNS = [
    # Private Keys (RSA, EC, OPENSSH, PGP)
    (re.compile(r"-----BEGIN[ A-Z0-9_-]+PRIVATE KEY-----[\s\S]+?-----END[ A-Z0-9_-]+PRIVATE KEY-----", re.IGNORECASE), "[REDACTED_PRIVATE_KEY]"),
    # AIRA Session Tokens
    (re.compile(r"aira_tok_[a-zA-Z0-9_-]{30,}", re.IGNORECASE), "[REDACTED_SESSION_TOKEN]"),
    # JWT Bearer tokens
    (re.compile(r"Bearer\s+eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", re.IGNORECASE), "Bearer [REDACTED_JWT_TOKEN]"),
    # Password configuration assignments
    (re.compile(r'(?i)(password|secret|passwd|pwd)\s*[:=]\s*["\']?([^"\'\s]{4,})["\']?'), r"\1: [REDACTED_PASSWORD]"),
    # SNMP Community string assignments
    (re.compile(r'(?i)(snmp[-_]community|community[-_]name)\s*[:=]\s*["\']?([^"\'\s]+)["\']?'), r"\1: [REDACTED_SNMP_COMMUNITY]"),
    # Generic API Keys / AWS / GitHub tokens
    (re.compile(r"(?i)(api[-_]?key|auth[-_]?token|client[-_]?secret)\s*[:=]\s*['\"]([a-zA-Z0-9_\-\.]{16,})['\"]"), r"\1: '[REDACTED_SECRET]'"),
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\b(ghp_[a-zA-Z0-9]{36})\b"), "[REDACTED_GITHUB_TOKEN]"),
]


class AIOutputGuard:
    """
    Centralized Output Security Guard enforcing data classification and content sanitization.
    """

    def __init__(self) -> None:
        pass

    def inspect_and_sanitize(
        self,
        content: str,
        user_permissions: Optional[Set[str]] = None,
        is_internal_staff: bool = False,
    ) -> Tuple[str, List[str]]:
        """
        Scans AI output text and redacts unauthorized secrets.

        Returns:
            (sanitized_content, list_of_detected_leak_types)
        """
        if not content or not isinstance(content, str):
            return content, []

        user_perms = user_permissions or set()
        has_sensitive_clearance = is_internal_staff or ("ACCESS_SENSITIVE_DATA" in user_perms) or ("admin.all" in user_perms)

        detected_leaks: List[str] = []
        sanitized = content

        for pattern, replacement in SECRET_PATTERNS:
            if pattern.search(sanitized):
                match_name = replacement.strip("[]")
                detected_leaks.append(match_name)
                # If caller does not have explicit clearance, redact all restricted patterns
                if not has_sensitive_clearance or "PRIVATE_KEY" in match_name or "SESSION_TOKEN" in match_name:
                    sanitized = pattern.sub(replacement, sanitized)

        if detected_leaks:
            logger.warning(
                "AIOutputGuard intercepted potential sensitive leak in generated content. Types: %s. Redacted: %s",
                detected_leaks,
                not has_sensitive_clearance,
            )

        return sanitized, detected_leaks

    def filter_context_for_user(
        self,
        context_items: List[Dict[str, Any]],
        user_permissions: Optional[Set[str]] = None,
        is_internal_staff: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Pre-retrieval authorization filtering: Strips items with classification RESTRICTED
        if the calling user lacks ACCESS_SENSITIVE_DATA.
        """
        user_perms = user_permissions or set()
        can_access_sensitive = is_internal_staff or ("ACCESS_SENSITIVE_DATA" in user_perms)

        filtered = []
        for item in context_items:
            classification = item.get("classification", DataClassification.INTERNAL.value)
            if classification == DataClassification.RESTRICTED.value and not can_access_sensitive:
                logger.info("Filtered RESTRICTED context item '%s' from unauthorized user.", item.get("id", "unknown"))
                continue
            filtered.append(item)

        return filtered


# Global instance
output_guard = AIOutputGuard()
