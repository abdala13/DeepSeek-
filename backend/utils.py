import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def split_csv_env(name: str, fallback: str = "") -> List[str]:
    value = os.getenv(name, fallback)
    return [x.strip() for x in value.split(",") if x.strip()]


def run_command(args: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> Dict[str, Any]:
    try:
        proc = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Command timed out", "returncode": 124}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": 1}
