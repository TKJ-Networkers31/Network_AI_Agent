import os
import tempfile
from pathlib import Path

# Arahkan temporary directory ke workspace drive jika C: sempit
_workspace_tmp = Path(__file__).resolve().parent / ".tmp"
_workspace_tmp.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("AIRA_TMP_DIR", str(_workspace_tmp))
if not os.environ.get("TEMP") or tempfile.gettempdir().startswith("C:"):
    tempfile.tempdir = str(_workspace_tmp)
