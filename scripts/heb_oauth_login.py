#!/usr/bin/env python3
"""One-time interactive HEB mobile OAuth login -> tokens.json.

This is the setup step for the durable, Incapsula-free bearer auth path
(``auth/oauth.py``). Unlike the Playwright cookie-capture path
(``capture_session.py``), this needs no browser automation and no
Chromium on the machine running the MCP server — handy for a
resource-constrained host (e.g. a Raspberry Pi) where you don't want to
also run headless Chrome for reese84 keep-warm.

The catch: the OAuth redirect URI is a mobile app deep link
(``com.heb.myheb://oauth2redirect?code=...``), which no desktop browser
will navigate to. So this is a two-step, copy/paste flow:

  1. `python scripts/heb_oauth_login.py start`
     Prints an authorization URL. Open it in any browser, log into your
     HEB account. When login succeeds, the browser will fail to open the
     final `com.heb.myheb://...` redirect (that's expected — no app is
     installed) but the URL bar / "open in app?" prompt will show the
     full redirect URL. Copy it.

  2. `python scripts/heb_oauth_login.py finish 'com.heb.myheb://oauth2redirect?code=...&state=...'`
     Exchanges the code for tokens and writes tokens.json next to your
     auth_state_path (default ``~/.texas-grocery-mcp/tokens.json``).

Verify with the `session_status` MCP tool afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from texas_grocery_mcp.auth.oauth import (  # noqa: E402
    OAuthError,
    build_auth_url,
    create_oauth_context,
    exchange_code,
    save_tokens,
)

CONTEXT_CACHE = Path.home() / ".texas-grocery-mcp" / ".oauth_pending.json"


def cmd_start(_args: argparse.Namespace) -> None:
    ctx = create_oauth_context()
    CONTEXT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_CACHE.write_text(
        json.dumps({"code_verifier": ctx.code_verifier, "state": ctx.state})
    )
    url = build_auth_url(ctx)
    print("1. Open this URL in a browser and log into your HEB account:\n")
    print(f"   {url}\n")
    print(
        "2. After login, the browser will try (and fail) to open a\n"
        "   com.heb.myheb://oauth2redirect?code=...&state=... link.\n"
        "   Copy that full URL (from the address bar, or an 'open app?'\n"
        "   prompt / the browser's navigation error page), then run:\n\n"
        "   python scripts/heb_oauth_login.py finish '<paste the URL here>'"
    )


def cmd_finish(args: argparse.Namespace) -> None:
    if not CONTEXT_CACHE.exists():
        print("ERROR: no pending login. Run 'start' first.", file=sys.stderr)
        sys.exit(1)
    pending = json.loads(CONTEXT_CACHE.read_text())

    parsed = urlparse(args.redirect_url)
    query = parse_qs(parsed.query)
    code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]

    if not code:
        print(f"ERROR: no 'code' param found in: {args.redirect_url}", file=sys.stderr)
        sys.exit(1)
    if state != pending["state"]:
        print("ERROR: state mismatch — run 'start' again and use its URL.", file=sys.stderr)
        sys.exit(1)

    try:
        tokens = exchange_code(code, pending["code_verifier"])
    except OAuthError as e:
        print(f"ERROR: token exchange failed: {e}", file=sys.stderr)
        sys.exit(1)

    now = time.time()
    tokens["obtained_at"] = now
    exp = datetime.fromtimestamp(now + float(tokens.get("expires_in", 1800)), tz=UTC)
    tokens["expires_at"] = exp.isoformat().replace("+00:00", "Z")

    auth_dir = args.auth_dir or (Path.home() / ".texas-grocery-mcp")
    save_tokens(auth_dir, tokens)
    CONTEXT_CACHE.unlink(missing_ok=True)

    print(f"Saved tokens to {auth_dir / 'tokens.json'}")
    print("Verify with the session_status MCP tool (should show authenticated: true).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Print the authorization URL to open in a browser")
    p_start.set_defaults(func=cmd_start)

    p_finish = sub.add_parser("finish", help="Exchange the redirect URL for tokens")
    p_finish.add_argument("redirect_url", help="The com.heb.myheb://oauth2redirect?... URL")
    p_finish.add_argument(
        "--auth-dir",
        type=Path,
        default=None,
        help="Directory to write tokens.json into (default: ~/.texas-grocery-mcp)",
    )
    p_finish.set_defaults(func=cmd_finish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
