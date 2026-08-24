from messages_mcp.contacts import looks_like_handle, normalize_handle
from messages_mcp.db import parse_attributed_body


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
