"""
agents/rei/settings_tools.py — future AI-tool contract for the Global
Settings Engine (Sprint 2.6, Worker 1).

This is a thin wrapper over core/global_settings.py, mirroring the shape
of agents/rei/fs_tools.py (which wraps core/filesystem/*): the functions
here are what a future REI tool schema would point at, so that AIRA never
touches the settings database directly.

    AIRA -> (future) settings tool schema -> functions in this file
         -> core/global_settings.py (validation + persistence)
         -> "settings.changed" on the existing Event Bus -> UI refresh

NOT wired into agents/rei/registry.py / REI_TOOLS / REI_TOOL_SCHEMAS yet -
per Sprint 2.6 scope, the tool registry is left untouched. Registering
this as an actual LLM-callable tool (with a schema entry, category, and
an entry in REI_TOOLS/REI_TOOL_CATEGORY/REI_TOOL_SCHEMAS) is a follow-up
step for whoever owns that integration next, exactly like fs_tools.py was
wired into registry.py in a prior sprint.
"""

from core.global_settings import read as _read
from core.global_settings import read_all as _read_all
from core.global_settings import write as _write


def get_setting(key: str) -> dict:
    result = _read(key)
    result["tool"] = "get_setting"
    return result


def list_settings() -> dict:
    result = _read_all()
    result["tool"] = "list_settings"
    return result


def update_setting(key: str, value) -> dict:
    result = _write(key, value)
    result["tool"] = "update_setting"
    return result
