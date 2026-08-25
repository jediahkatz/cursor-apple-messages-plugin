# Technical notes

## Requirements

- macOS
- Apple Messages signed in
- Cursor with third-party plugins enabled
- Full Disk Access and Automation permissions granted during onboarding

## Install

Paste this repository URL into Cursor's plugin search:

```text
https://github.com/jediahkatz/cursor-apple-messages-plugin
```

For local development:

```bash
mkdir -p ~/.cursor/plugins/local
ln -sf /path/to/cursor-messages ~/.cursor/plugins/local/messages
```

Then run **Developer: Reload Window**.

## How it works

The plugin is local-only:

- Reads `~/Library/Messages/chat.db` for history and new-message detection.
- Sends through Messages.app with AppleScript.
- Resolves names through Contacts.
- Stores access and confirmation state in `~/.cursor/messages`.
- Runs a Python MCP server over stdio.
- Builds its SwiftUI onboarding and confirmation helpers on demand.

No external service, API token, or message relay is used.

## Permissions

The native onboarding window requests:

- Messages Automation
- Contacts Automation
- Full Disk Access

macOS requires the user to approve these permissions. Full Disk Access may require restarting Cursor.

Reopen onboarding with:

```bash
./bin/messages-mcp onboard
```

## Tools

- `send_message` — send to a name, phone number, Apple ID email, or chat ID
- `reply` — reply to an existing chat ID
- `chat_messages` — fetch recent history
- `list_chats` — list recent conversations
- `find_contact` — resolve a contact name
- `check_inbox` — fetch messages received after the server watermark
- `messages_status` — inspect database and access status

## Access control

Inbound and history access use an empty allowlist by default. The user's own Messages addresses are always permitted so self-chat testing works.

```text
/messages-access allow +15551234567
```

Access changes must originate in Cursor, never from an incoming message.

## Send confirmation

`send_message` and `reply` use a native `beforeMCPExecution` confirmation with **Skip**, **Send**, and **Always Send** actions. The direct CLI send command also confirms.

Cursor hooks apply to calls dispatched through Cursor's hook pipeline. Other MCP clients and direct transport calls are outside that client-side boundary, so server-side fallback enforcement is planned as defense in depth.

Reset confirmation bypasses with:

```bash
./bin/messages-mcp reset-confirmations
```

## CLI

```bash
./bin/messages-mcp status
./bin/messages-mcp find "Name"
./bin/messages-mcp send --to "Name" --text "Hello"
```

With no arguments, `messages-mcp` runs the stdio MCP server.

## Environment

- `MESSAGES_APPEND_SIGNATURE` — append `Sent by Cursor`
- `MESSAGES_ALLOW_SMS` — also accept inbound SMS/RCS
- `MESSAGES_STATE_DIR` — override `~/.cursor/messages`
- `MESSAGES_DB_PATH` — override `~/Library/Messages/chat.db`

Cursor does not currently inject incoming texts as agent events. Use `check_inbox` or `chat_messages`.
