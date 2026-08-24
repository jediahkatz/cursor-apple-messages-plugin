from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from messages_mcp.access import STATE_DIR
from messages_mcp.db import CHAT_DB

PERMS_FILE = STATE_DIR / "perms.json"
FDA_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
AUTOMATION_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def onboard_binary() -> Path:
    # Filename doubles as the window's app name in the menu bar and Dock.
    return plugin_root() / "bin" / "Messages for Cursor"


def _osascript(script: str, timeout: float = 5.0) -> bool:
    wrapped = f"with timeout of {max(1, int(timeout) - 1)} seconds\n{script}\nend timeout\n"
    try:
        res = subprocess.run(
            ["osascript", "-"],
            input=wrapped,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return res.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _open_url(url: str) -> None:
    try:
        subprocess.run(["open", url], capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass


def _load() -> dict:
    try:
        return json.loads(PERMS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PERMS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(PERMS_FILE)
    except OSError as exc:
        sys.stderr.write(f"messages: perms state save failed: {exc}\n")


def chat_db_readable() -> bool:
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True, timeout=2)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def _ensure_binary() -> Path | None:
    path = onboard_binary()
    if path.is_file() and os.access(path, os.X_OK):
        return path
    build = plugin_root() / "macos" / "build.sh"
    if not build.is_file():
        return None
    try:
        subprocess.run(["bash", str(build)], check=True, timeout=60, capture_output=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        sys.stderr.write(f"messages: onboarding build failed: {exc}\n")
        return None
    return path if path.is_file() else None


def show_onboarding(*, force: bool = False) -> None:
    """Open the ChatGPT-style permission window. Not an MCP tool."""
    if os.environ.get("MESSAGES_SKIP_PERM_PROMPT", "").lower() in {"1", "true", "yes"}:
        return
    state = _load()
    # contacts_ok was added when Contacts became its own real permission
    # step. Re-open once for installs completed by an older onboarding build.
    if not force and state.get("onboarding_complete") and state.get("contacts_ok"):
        return
    binary = _ensure_binary()
    if binary is None:
        sys.stderr.write("messages: onboarding helper missing; falling back to Settings panes\n")
        _fallback_prompt(state)
        return
    sys.stderr.write("messages: opening permission onboarding\n")
    try:
        subprocess.Popen(
            [str(binary)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        sys.stderr.write(f"messages: failed to launch onboarding: {exc}\n")
        _fallback_prompt(state)
        return
    state["onboarding_shown"] = time.time()
    _save(state)


def _fallback_prompt(state: dict) -> None:
    _osascript('tell application "Contacts" to get count of people')
    messages_ok = _osascript(
        """
        tell application "Messages"
          if (count of accounts) > 0 then
            get id of 1st account
          end if
        end tell
        """
    )
    if not messages_ok and not state.get("automation_pane_opened"):
        _open_url(AUTOMATION_PANE)
        state["automation_pane_opened"] = time.time()
    if not chat_db_readable() and not state.get("fda_pane_opened"):
        try:
            CHAT_DB.open("rb").close()
        except OSError:
            pass
        _open_url(FDA_PANE)
        state["fda_pane_opened"] = time.time()
    state["last_prompt"] = time.time()
    _save(state)


def start_permission_prompts() -> None:
    threading.Thread(target=show_onboarding, name="messages-perms", daemon=True).start()
