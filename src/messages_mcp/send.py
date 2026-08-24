from __future__ import annotations

import os
import subprocess
from pathlib import Path

SEND_TO_CHAT = """on run argv
  with timeout of 20 seconds
    tell application "Messages" to send (item 1 of argv) to chat id (item 2 of argv)
  end timeout
end run
"""

SEND_FILE_TO_CHAT = """on run argv
  with timeout of 20 seconds
    tell application "Messages" to send (POSIX file (item 1 of argv)) to chat id (item 2 of argv)
  end timeout
end run
"""

SEND_TO_PARTICIPANT = """on run argv
  with timeout of 20 seconds
    tell application "Messages"
      set targetService to 1st account whose service type = iMessage
      set targetBuddy to participant (item 2 of argv) of targetService
      send (item 1 of argv) to targetBuddy
    end tell
  end timeout
end run
"""

SEND_FILE_TO_PARTICIPANT = """on run argv
  with timeout of 20 seconds
    tell application "Messages"
      set targetService to 1st account whose service type = iMessage
      set targetBuddy to participant (item 2 of argv) of targetService
      send (POSIX file (item 1 of argv)) to targetBuddy
    end tell
  end timeout
end run
"""

SEND_TO_BUDDY = """on run argv
  with timeout of 20 seconds
    tell application "Messages"
      send (item 1 of argv) to buddy (item 2 of argv) of (1st service whose service type = iMessage)
    end tell
  end timeout
end run
"""


def _run_osascript(script: str, *argv: str) -> str | None:
    try:
        res = subprocess.run(
            ["osascript", "-", *argv],
            input=script,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except FileNotFoundError:
        return "osascript not found (macOS only)"
    except subprocess.TimeoutExpired:
        return "osascript timed out — Messages.app may be waiting for an Automation permission prompt"
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        return err or f"osascript exit {res.returncode}"
    return None


def send_text_to_chat(chat_id: str, text: str) -> str | None:
    return _run_osascript(SEND_TO_CHAT, text, chat_id)


def send_file_to_chat(chat_id: str, path: str) -> str | None:
    return _run_osascript(SEND_FILE_TO_CHAT, path, chat_id)


def send_text_to_handle(handle: str, text: str) -> str | None:
    err = _run_osascript(SEND_TO_PARTICIPANT, text, handle)
    if err is None:
        return None
    return _run_osascript(SEND_TO_BUDDY, text, handle) or err


def send_file_to_handle(handle: str, path: str) -> str | None:
    return _run_osascript(SEND_FILE_TO_PARTICIPANT, path, handle)


def assert_sendable_path(path: str, state_dir: Path) -> None:
    real = Path(path).expanduser().resolve()
    if not real.exists() or not real.is_file():
        raise FileNotFoundError(path)
    try:
        state_real = state_dir.resolve()
    except OSError:
        return
    if state_real.exists() and real.is_relative_to(state_real):
        raise PermissionError(f"refusing to send plugin state: {path}")
    max_bytes = 100 * 1024 * 1024
    if real.stat().st_size > max_bytes:
        raise ValueError(f"file too large: {path} (max 100MB)")


def append_signature(text: str) -> str:
    if os.environ.get("MESSAGES_APPEND_SIGNATURE", "").lower() in {"1", "true", "yes"}:
        if not text.endswith("Sent by Cursor"):
            return text + "\nSent by Cursor"
    return text
