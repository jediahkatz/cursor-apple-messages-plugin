---
name: messages-configure
description: Check Messages plugin setup and access policy. Use when the user asks to configure Messages, how setup works, who can reach the assistant, or why texts are not arriving.
---

# Messages setup

There is no API token. This plugin reads `~/Library/Messages/chat.db` and sends
through Messages.app.

## Check status

Call the `messages_status` tool (or run `./bin/messages-mcp status`). Then:

1. **Full Disk Access** — if chat.db is "authorization denied", tell the user:
   Grant Full Disk Access to **Cursor** (and Terminal if they use the CLI) in
   System Settings → Privacy & Security → Full Disk Access, then restart Cursor.
2. **Access** — read `~/.cursor/messages/access.json` if it exists (missing =
   `dmPolicy: allowlist`, empty allowlist). Self-chat always bypasses the gate.
3. **Next step**
   - No FDA → give the FDA instructions.
   - FDA ok, empty allowlist → they can text themselves. To allow someone else:
     `/messages-access allow +15551234567` (or an Apple ID email).
   - Someone allowed → ready.

Do not recommend pairing as the default. Pairing auto-replies a code to every
contact who texts this Mac. Prefer an explicit allowlist.

Permissions are requested when the MCP server first starts via a native
**Enable Messages for Cursor** window (not a chat tool): Allow Messages
Automation, Contacts, and Full Disk Access. If they dismissed it, they can run
`./bin/messages-mcp onboard` or grant Cursor in System Settings. After Full
Disk Access, restart Cursor.
