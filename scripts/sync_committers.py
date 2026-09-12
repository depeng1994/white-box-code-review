#!/usr/bin/env python3
"""Fetch the Committer/Maintainer list from CANN community and update app.js."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

GITCODE_CONTENTS_API = (
    "https://api.gitcode.com/api/v5/repos"
    "/cann/community/contents"
    "/CANN/sigs/framework-adapter/README.md"
)

ENTRY_RE = re.compile(
    r"-\s+[^[]*\[@(?P<login>[a-zA-Z0-9_-]+)\]"
    r"\(https://gitcode\.com/[a-zA-Z0-9_-]+\)"
)


@dataclass
class CommitterSyncResult:
    logins: list[str]
    changed: bool


def fetch_readme(token: str) -> str:
    req = urllib.request.Request(GITCODE_CONTENTS_API)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            raw_content = data.get("content")
            if not raw_content:
                raise RuntimeError("API response missing 'content' field")
            return base64.b64decode(raw_content).decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitCode API HTTP {exc.code}: {body}") from exc


def parse_logins(markdown: str) -> list[str]:
    seen: set[str] = set()
    logins: list[str] = []
    in_scope = False

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("###"):
            lower = stripped.lower()
            in_scope = "maintainer" in lower or "committer" in lower
            continue
        if not in_scope:
            continue
        m = ENTRY_RE.match(stripped)
        if m:
            login = m.group("login")
            if login not in seen:
                seen.add(login)
                logins.append(login)
    return logins


def build_committer_js(logins: list[str]) -> str:
    entries = ",\n  ".join(f'"{login}"' for login in sorted(logins))
    return f"""const COMMITTER_USERS = new Set([
  {entries},
]);
"""


def update_app_js(app_js_path: Path, new_block: str) -> bool:
    original = app_js_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"const COMMITTER_USERS = new Set\(\[[^]]*\]\);",
        re.MULTILINE | re.DOTALL,
    )
    replaced, count = pattern.subn(new_block.rstrip(), original, count=1)
    if count == 0:
        raise RuntimeError(
            "Could not find 'const COMMITTER_USERS = new Set([…]);' in "
            f"{app_js_path}"
        )
    if replaced == original:
        return False
    app_js_path.write_text(replaced, encoding="utf-8")
    return True


def run(*, app_js: Path, token: str, dry_run: bool = False) -> CommitterSyncResult:
    markdown = fetch_readme(token)
    logins = parse_logins(markdown)
    if not logins:
        raise RuntimeError("Parsed zero logins; upstream format may have changed")
    logins.sort()
    print(
        "found "
        f"{len(logins)} committers/maintainers from SIG README: {', '.join(logins)}"
    )
    if dry_run:
        print("dry-run: would write:", build_committer_js(logins))
        return CommitterSyncResult(logins=logins, changed=False)

    new_block = build_committer_js(logins)
    changed = update_app_js(app_js, new_block)
    print(f"updated {app_js} (changed)" if changed else f"{app_js} already up to date")
    return CommitterSyncResult(logins=logins, changed=changed)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Committer/Maintainer list into app.js"
    )
    parser.add_argument(
        "--app-js",
        type=Path,
        default=ROOT / "demo" / "app.js",
        help="Path to app.js (default: demo/app.js)",
    )
    parser.add_argument(
        "--token-env",
        default="GITCODE_API_TOKEN",
        help="Environment variable holding the GitCode API token",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the new block without writing",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    token = os.environ.get(args.token_env, "")
    if not token:
        print(f"error: ${args.token_env} is not set", file=sys.stderr)
        return 1
    try:
        run(app_js=args.app_js.resolve(), token=token, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
