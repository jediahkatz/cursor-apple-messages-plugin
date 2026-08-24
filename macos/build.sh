#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# The filename is the app's display name in the menu bar and Dock.
OUT="$ROOT/bin/Messages for Cursor"
SDK="$(xcrun --show-sdk-path 2>/dev/null || true)"
if [[ -z "${SDK}" ]]; then
  echo "xcrun SDK not found" >&2
  exit 1
fi
xcrun swiftc -parse-as-library "$ROOT/macos/Onboarding.swift" \
  -o "$OUT" \
  -sdk "$SDK" \
  -framework SwiftUI -framework AppKit \
  -framework ApplicationServices -framework CoreServices \
  -lsqlite3
chmod +x "$OUT"
echo "built $OUT"
