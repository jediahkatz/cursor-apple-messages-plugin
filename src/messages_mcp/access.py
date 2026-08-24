from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("MESSAGES_STATE_DIR", Path.home() / ".cursor" / "messages"))
ACCESS_FILE = STATE_DIR / "access.json"


def default_access() -> dict[str, Any]:
    return {
        "dmPolicy": "allowlist",
        "allowFrom": [],
        "groups": {},
        "mentionPatterns": [],
    }


def load_access() -> dict[str, Any]:
    try:
        raw = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default_access()
    except json.JSONDecodeError:
        corrupt = ACCESS_FILE.with_suffix(f".json.corrupt-{os.getpid()}")
        try:
            ACCESS_FILE.replace(corrupt)
        except OSError:
            pass
        return default_access()
    policy = raw.get("dmPolicy")
    return {
        "dmPolicy": policy if policy in {"allowlist", "disabled"} else "allowlist",
        "allowFrom": list(raw.get("allowFrom") or []),
        "groups": dict(raw.get("groups") or {}),
        "mentionPatterns": list(raw.get("mentionPatterns") or []),
    }
