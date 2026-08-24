import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import messages_mcp.server as server_module
from messages_mcp.confirm import handle_event
from messages_mcp.contacts import ContactMatch, looks_like_handle, normalize_handle
from messages_mcp.db import parse_attributed_body
from messages_mcp.server import DeliveryError, MessagesServer


def test_normalize_us_phone() -> None:
    assert normalize_handle("(214) 555-0100") == "+12145550100"
    assert normalize_handle("12145550100") == "+12145550100"
    assert normalize_handle("+1 214 555 0100") == "+12145550100"


def test_normalize_email() -> None:
    assert normalize_handle("Name@ICloud.com") == "name@icloud.com"


def test_looks_like_handle() -> None:
    assert looks_like_handle("+15551234567")
    assert looks_like_handle("person@icloud.com")
    assert not looks_like_handle("Christina Lu")


def test_parse_attributed_body_small_length() -> None:
    payload = b"hello"
    blob = b"NSString" + b"\x00\x2b" + bytes([len(payload)]) + payload
    assert parse_attributed_body(blob) == "hello"


def test_partial_delivery_is_not_retried_to_another_handle() -> None:
    server = object.__new__(MessagesServer)
    attempts: list[str] = []

    def deliver(*, chat_id: str | None, handle: str | None, text: str, files: list[str]) -> str:
        assert chat_id is None
        assert handle is not None
        attempts.append(handle)
        raise DeliveryError("attachment failed", sent=1)

    original_lookup = server_module.lookup_contacts
    server._deliver = deliver  # type: ignore[method-assign]
    server_module.lookup_contacts = lambda _: [
        ContactMatch("Person", ["+15550000001", "+15550000002"], [])
    ]
    try:
        try:
            server.tool_send("Person", "hello", [])
        except DeliveryError:
            pass
        else:
            raise AssertionError("partial delivery should fail")
    finally:
        server_module.lookup_contacts = original_lookup

    assert attempts == ["+15550000001"]


def confirmation_event() -> dict:
    return {
        "conversation_id": "cursor-chat-1",
        "command": "./bin/messages-mcp",
        "tool_name": "send_message",
        "tool_input": {"to": "+15550000001", "text": "Hello"},
    }


def test_send_can_suppress_future_prompts_for_cursor_chat() -> None:
    with tempfile.TemporaryDirectory() as directory:
        state_file = Path(directory) / "confirmations.json"
        confirm = Mock(return_value={"decision": "send", "suppress": True})

        assert handle_event(
            confirmation_event(), confirm=confirm, state_file=state_file, platform="darwin"
        ) == {"permission": "allow"}
        assert handle_event(
            confirmation_event(), confirm=confirm, state_file=state_file, platform="darwin"
        ) == {"permission": "allow"}
        confirm.assert_called_once_with(confirmation_event()["tool_input"], True)


def test_skip_denies_send() -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = handle_event(
            confirmation_event(),
            confirm=lambda _args, _can_suppress: {"decision": "skip", "suppress": False},
            state_file=Path(directory) / "confirmations.json",
            platform="darwin",
        )
    assert result["permission"] == "deny"


def test_unrelated_mcp_tool_is_allowed_without_prompt() -> None:
    event = confirmation_event()
    event["command"] = "another-mcp-server"
    confirm = Mock()

    assert handle_event(event, confirm=confirm, platform="darwin") == {"permission": "allow"}
    confirm.assert_not_called()


def test_real_hook_json_input_and_invalid_state_shape() -> None:
    event = confirmation_event()
    event["tool_input"] = json.dumps(event["tool_input"])
    with tempfile.TemporaryDirectory() as directory:
        state_file = Path(directory) / "confirmations.json"
        state_file.write_text("[]", encoding="utf-8")
        result = handle_event(
            event,
            confirm=lambda _args, _can_suppress: {"decision": "send", "suppress": False},
            state_file=state_file,
            platform="darwin",
        )
    assert result == {"permission": "allow"}
