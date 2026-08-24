from __future__ import annotations

import argparse
import sys

from messages_mcp.permissions import show_onboarding
from messages_mcp.server import MessagesServer, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="messages-mcp", description="Cursor Messages MCP server")
    sub = parser.add_subparsers(dest="cmd")

    send = sub.add_parser("send", help="Send one message through Apple Messages")
    send.add_argument("--to", required=True, help="Contact name, phone, email, or chat_id")
    send.add_argument("--text", required=True)
    send.add_argument("--file", action="append", default=[], dest="files")

    sub.add_parser("status", help="Show chat.db and access status")
    find = sub.add_parser("find", help="Look up a contact")
    find.add_argument("query")
    sub.add_parser("onboard", help="Show the Messages permission onboarding window")

    args = parser.parse_args(argv)
    if args.cmd is None:
        serve()
        return 0
    if args.cmd == "onboard":
        show_onboarding(force=True)
        return 0

    server = MessagesServer()
    try:
        if args.cmd == "send":
            print(server.tool_send(args.to, args.text, args.files))
        elif args.cmd == "status":
            print(server.tool_status())
        elif args.cmd == "find":
            print(server.tool_find(args.query))
        else:
            parser.error("unknown command")
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
