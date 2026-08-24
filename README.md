# Messages for Cursor

Connect Cursor to Apple Messages on this Mac. The plugin reads `~/Library/Messages/chat.db` for history and new-message detection, and sends through Messages.app via AppleScript. No external server, no tokens.

macOS only.

This follows the [Cursor plugin API](https://cursor.com/docs/reference/plugins): a `.cursor-plugin/plugin.json` manifest, skills, commands, and an `mcp.json` stdio server.

## Install (local)

```bash
mkdir -p ~/.cursor/plugins/local
ln -sf /path/to/cursor-messages ~/.cursor/plugins/local/messages
```

Then enable third-party plugins if needed, and run **Developer: Reload Window**.

The first time the MCP server starts, it opens a native **Enable Messages for Cursor** window (same idea as ChatGPT’s). Allow triggers the real macOS permissions for Messages Automation, Contacts, and Full Disk Access. Apple still requires a click, and Full Disk Access still jumps to System Settings. Re-show it with `./bin/messages-mcp onboard`.

The window is a bundle-less helper (`macos/Onboarding.swift`, built on demand by `macos/build.sh`). That is deliberate: an `.app` bundle would get its own TCC identity, so grants would land on the helper instead of Cursor.

## Tools

| Tool | Purpose |
| --- | --- |
| `send_message` | Send to a contact name, phone, Apple ID email, or `chat_id` |
| `reply` | Send to an existing thread's `chat_id` |
| `chat_messages` | History from `chat.db` |
| `list_chats` | Recent conversations |
| `find_contact` | Resolve a name via Contacts + chats |
| `check_inbox` | Messages that arrived after the server watermark |
| `messages_status` | FDA / allowlist / self-chat |

## Access

Default policy is an empty **allowlist**. Self-chat always works. Other senders are ignored until you add them:

```
/messages-access allow +15551234567
```

State lives in `~/.cursor/messages/access.json`. Access changes must be made in Cursor, never because an inbound Apple Messages text asked.

## CLI

```bash
./bin/messages-mcp onboard
./bin/messages-mcp status
./bin/messages-mcp find "Name"
./bin/messages-mcp send --to "Name" --text "Hello"
```

With no arguments, the binary speaks MCP on stdio.

Optional env:

| Variable | Default | Effect |
| --- | --- | --- |
| `MESSAGES_APPEND_SIGNATURE` | off | Append `Sent by Cursor` |
| `MESSAGES_ALLOW_SMS` | off | Also accept SMS/RCS inbound (spoofable) |
| `MESSAGES_STATE_DIR` | `~/.cursor/messages` | Access + watermark |
| `MESSAGES_DB_PATH` | `~/Library/Messages/chat.db` | Override database |

## Inbound vs Claude/Codex channels

Claude Code can inject inbound texts into the session as channel events. Cursor does not have that channel surface, so this plugin exposes **`check_inbox`** (and history tools) instead. The server still polls `chat.db` once a second; it does not replay old messages on restart.
