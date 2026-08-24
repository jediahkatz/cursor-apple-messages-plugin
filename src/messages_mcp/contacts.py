from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ContactMatch:
    name: str
    phones: list[str]
    emails: list[str]


def normalize_handle(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return raw
    if "@" in raw:
        return raw.lower()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if raw.startswith("+") and digits:
        return "+" + digits
    return raw


def looks_like_handle(value: str) -> bool:
    raw = (value or "").strip()
    if "@" in raw:
        return True
    digits = re.sub(r"\D", "", raw)
    return len(digits) >= 10


def lookup_contacts(query: str, timeout: float = 20.0) -> list[ContactMatch]:
    """Resolve people in macOS Contacts whose name contains `query`."""
    q = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Contacts"
  set thePeople to people whose name contains "{q}"
  set out to {{}}
  repeat with p in thePeople
    set phoneVals to {{}}
    repeat with ph in phones of p
      set end of phoneVals to (value of ph as string)
    end repeat
    set emailVals to {{}}
    repeat with em in emails of p
      set end of emailVals to (value of em as string)
    end repeat
    set phoneJoined to my joinList(phoneVals, ",")
    set emailJoined to my joinList(emailVals, ",")
    set end of out to (name of p as string) & tab & phoneJoined & tab & emailJoined
  end repeat
  set AppleScript's text item delimiters to linefeed
  return out as text
end tell

on joinList(lst, delim)
  set AppleScript's text item delimiters to delim
  set s to lst as text
  set AppleScript's text item delimiters to ""
  return s
end joinList
'''
    try:
        res = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if res.returncode != 0:
        return []
    matches: list[ContactMatch] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        name = parts[0].strip()
        phones = [normalize_handle(p) for p in (parts[1].split(",") if len(parts) > 1 and parts[1] else []) if p]
        emails = [e.strip().lower() for e in (parts[2].split(",") if len(parts) > 2 and parts[2] else []) if e]
        matches.append(ContactMatch(name=name, phones=phones, emails=emails))
    return matches


def handles_for_contact(match: ContactMatch) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for h in [*match.phones, *match.emails]:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out
