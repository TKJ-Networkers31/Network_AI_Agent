"""
core/external_context/config.py — provider configuration loading
(Sprint 2.7 / W7).

Follows the SAME pattern core/location/geo.py and
agents/rei/provider_client.py already use for external services: secrets
come from the process environment (.env loaded by the process, e.g. via
python-dotenv at app startup - this module does not load dotenv itself,
matching the existing convention of not re-implementing that in every
module that needs a key), never from a database row, never from a literal
in source. This module is the ONE place that reads the Google Maps
environment variables; adapters receive an already-built
GoogleMapsConfig instead of touching os.environ themselves.

The API key is NEVER included in to_dict()/logging - GoogleMapsConfig.to_dict()
only ever exposes whether a key is present (has_api_key), the same masking
convention core/model_registry.py::_row_to_dict uses for its `api_key`
column (mask_api_key -> has_api_key).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from core.external_context.constants import DEFAULT_TIMEOUT_SECONDS

ENV_API_KEY = "GOOGLE_MAPS_API_KEY"
ENV_TIMEOUT = "GOOGLE_MAPS_TIMEOUT_SECONDS"
ENV_ENABLED = "GOOGLE_MAPS_ENABLED"

_FALSE_VALUES = {"0", "false", "off", "no"}


def _read_timeout(raw: Optional[str]) -> float:
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS

    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class GoogleMapsConfig:
    """
    Immutable snapshot of Google Maps provider configuration.

    api_key : the raw secret. Kept OUT of to_dict()/repr-safe serialization
              on purpose - callers that need to know "is this configured"
              use `has_api_key` / `is_configured`, never the key itself.
    enabled : an explicit kill switch independent of whether a key is
              present (mirrors api/ws_bridge.py::stream_enabled_for_turn's
              AIRA_STREAMING env kill switch) - ops can disable the
              provider without unsetting the key.
    """

    api_key: Optional[str] = None
    enabled: bool = True
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def is_configured(self) -> bool:
        return self.enabled and self.has_api_key

    def to_dict(self) -> dict:
        """JSON/log-safe view - api_key itself is NEVER included."""
        return {
            "has_api_key": self.has_api_key,
            "enabled": self.enabled,
            "is_configured": self.is_configured,
            "timeout_seconds": self.timeout_seconds,
        }


def load_google_maps_config(env: Optional[dict] = None) -> GoogleMapsConfig:
    """
    Build a GoogleMapsConfig from the process environment (or an injected
    mapping, for tests - same Dependency Injection style as
    core/context/builder.py::ContextBuilder). Never raises: a missing or
    malformed environment produces a config with has_api_key=False /
    is_configured=False rather than an exception, so a provider built from
    it can report itself as unavailable through the normal
    is_available()/QueryResult.fail() path instead of crashing at import
    or construction time.
    """
    source = env if env is not None else os.environ

    api_key = source.get(ENV_API_KEY)
    api_key = api_key.strip() if isinstance(api_key, str) else None

    enabled_raw = source.get(ENV_ENABLED)
    enabled = True if enabled_raw is None else str(enabled_raw).strip().lower() not in _FALSE_VALUES

    timeout = _read_timeout(source.get(ENV_TIMEOUT))

    return GoogleMapsConfig(api_key=api_key or None, enabled=enabled, timeout_seconds=timeout)
