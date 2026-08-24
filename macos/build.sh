#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# The filename is the app's display name in the menu bar and Dock.
OUT="$ROOT/bin/Messages for Cursor"
CONFIRM_OUT="$ROOT/bin/confirmation/Messages for Cursor"
TARGET="${1:-all}"
SDK="$(xcrun --show-sdk-path 2>/dev/null || true)"
if [[ -z "${SDK}" ]]; then
  echo "xcrun SDK not found" >&2
  exit 1
fi

build_onboarding() {
  local tmp="$OUT.tmp.$$"
  if ! xcrun swiftc -parse-as-library "$ROOT/macos/Onboarding.swift" \
    -o "$tmp" \
    -sdk "$SDK" \
    -framework SwiftUI -framework AppKit \
    -framework ApplicationServices -framework CoreServices \
    -lsqlite3; then
    rm -f "$tmp"
    return 1
  fi
  chmod +x "$tmp"
  mv "$tmp" "$OUT"
  echo "built $OUT"
}

build_confirmation() {
  mkdir -p "$(dirname "$CONFIRM_OUT")"
  local tmp="$CONFIRM_OUT.tmp.$$"
  if ! xcrun swiftc "$ROOT/macos/ConfirmSend.swift" \
    -o "$tmp" \
    -sdk "$SDK" \
    -framework AppKit -framework SwiftUI; then
    rm -f "$tmp"
    return 1
  fi
  chmod +x "$tmp"
  mv "$tmp" "$CONFIRM_OUT"
  echo "built $CONFIRM_OUT"
}

case "$TARGET" in
  all)
    build_onboarding
    build_confirmation
    ;;
  onboarding) build_onboarding ;;
  confirmation) build_confirmation ;;
  *)
    echo "unknown build target: $TARGET" >&2
    exit 2
    ;;
esac
