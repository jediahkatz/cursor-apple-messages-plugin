from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("MESSAGES_STATE_DIR", Path.home() / ".cursor" / "messages"))
ACCESS_FILE = STATE_DIR / "access.json"
WATERMARK_FILE = STATE_DIR / "watermark"


def default_access() -> dict[str, Any]:
    return {
        "dmPolicy": "allowlist",
        "allowFrom": [],
        "groups": {},
        "pending": {},
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
    data = default_access()
    data.update({k: v for k, v in raw.items() if k in data or k in ("mentionPatterns", "textChunkLimit", "chunkMode")})
    data["dmPolicy"] = raw.get("dmPolicy", "allowlist")
    data["allowFrom"] = list(raw.get("allowFrom") or [])
    data["groups"] = dict(raw.get("groups") or {})
    data["pending"] = dict(raw.get("pending") or {})
    if "mentionPatterns" in raw:
        data["mentionPatterns"] = raw["mentionPatterns"]
    if "textChunkLimit" in raw:
        data["textChunkLimit"] = raw["textChunkLimit"]
    if "chunkMode" in raw:
        data["chunkMode"] = raw["chunkMode"]
    return data


def save_access(access: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ACCESS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(access, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(ACCESS_FILE)


def allowed_handles(self_handles: set[str]) -> set[str]:
    access = load_access()
    out = {h.lower() for h in access.get("allowFrom") or []}
    out.update(self_handles)
    return out


def group_guids() -> set[str]:
    access = load_access()
    return set((access.get("groups") or {}).keys())
