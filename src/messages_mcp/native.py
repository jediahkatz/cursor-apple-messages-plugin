from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_binary(filename: str, build_target: str) -> Path | None:
    if sys.platform != "darwin":
        return None
    root = plugin_root()
    path = root / "bin" / filename
    if path.is_file() and os.access(path, os.X_OK):
        return path
    build = root / "macos" / "build.sh"
    if not build.is_file():
        return None
    try:
        import fcntl

        with (root / "bin" / ".native-build.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if path.is_file() and os.access(path, os.X_OK):
                return path
            subprocess.run(
                ["bash", str(build), build_target],
                check=True,
                timeout=60,
                capture_output=True,
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        sys.stderr.write(f"messages: native helper build failed: {exc}\n")
        return None
    return path if path.is_file() and os.access(path, os.X_OK) else None
