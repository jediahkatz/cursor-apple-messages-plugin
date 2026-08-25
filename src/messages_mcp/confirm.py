from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypedDict

from messages_mcp.access import STATE_DIR
from messages_mcp.native import ensure_binary

CONFIRMATIONS_FILE = STATE_DIR / "confirmations.json"
MCP_SERVER_NAME = "messages"
SEND_TOOLS = {"send_message", "reply"}


class ConfirmationDecision(TypedDict):
    decision: Literal["send", "skip"]
    suppress: bool


def _is_messages_send(event: dict[str, Any]) -> bool:
    return (
        event.get("mcp_server_name") == MCP_SERVER_NAME
        and event.get("tool_name") in SEND_TOOLS
    )


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("tool_input", {})
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("tool_input must be a JSON object")


def _load_suppressed(path: Path) -> dict[str, float]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        values = raw.get("suppressedConversations", {})
        if not isinstance(values, dict):
            return {}
        return {str(key): float(value) for key, value in values.items()}
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def _suppress(conversation_id: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import fcntl

    with path.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        values = _load_suppressed(path)
        values[conversation_id] = time.time()
        if len(values) > 500:
            values = dict(sorted(values.items(), key=lambda item: item[1], reverse=True)[:500])
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as tmp:
            json.dump({"suppressedConversations": values}, tmp, indent=2)
            tmp.write("\n")
        tmp_path = Path(tmp.name)
        try:
            tmp_path.chmod(0o600)
            tmp_path.replace(path)
        finally:
            tmp_path.unlink(missing_ok=True)


def reset_suppressions(path: Path = CONFIRMATIONS_FILE) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def request_confirmation(
    args: dict[str, Any], can_suppress: bool = False
) -> ConfirmationDecision:
    binary = ensure_binary("confirmation/Messages for Cursor", "confirmation")
    if binary is None:
        raise RuntimeError("Messages confirmation helper is unavailable")
    payload = {
        "recipient": args.get("to") or args.get("chat_id") or "Unknown conversation",
        "text": str(args.get("text") or ""),
        "files": [str(path) for path in args.get("files") or []],
        "canSuppress": can_suppress,
    }
    result = subprocess.run(
        [str(binary)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=225,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"confirmation helper exited {result.returncode}")
    raw = json.loads(result.stdout)
    if not isinstance(raw, dict) or raw.get("decision") not in {"send", "skip"}:
        raise RuntimeError("confirmation helper returned an invalid decision")
    suppress = raw.get("suppress", False)
    if not isinstance(suppress, bool):
        raise RuntimeError("confirmation helper returned an invalid suppression value")
    return {"decision": raw["decision"], "suppress": suppress}


def handle_event(
    event: dict[str, Any],
    *,
    confirm: Callable[[dict[str, Any], bool], ConfirmationDecision] = request_confirmation,
    state_file: Path = CONFIRMATIONS_FILE,
    platform: str = sys.platform,
) -> dict[str, str]:
    if platform != "darwin" or not _is_messages_send(event):
        return {"permission": "allow"}

    conversation_id = str(event.get("conversation_id") or "")
    if conversation_id and conversation_id in _load_suppressed(state_file):
        return {"permission": "allow"}

    decision = confirm(_tool_input(event), bool(conversation_id))
    if decision["decision"] == "skip":
        return {
            "permission": "deny",
            "user_message": "Message sending was skipped.",
            "agent_message": "The user skipped the native Apple Messages confirmation.",
        }
    if conversation_id and decision.get("suppress"):
        _suppress(conversation_id, state_file)
    return {"permission": "allow"}


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
        response = handle_event(event)
    except Exception as exc:  # fail closed with a useful message
        response = {
            "permission": "deny",
            "user_message": f"Message sending was blocked: {exc}",
            "agent_message": "The Apple Messages confirmation hook failed closed.",
        }
    json.dump(response, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
