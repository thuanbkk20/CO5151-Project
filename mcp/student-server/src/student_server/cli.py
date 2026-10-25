"""`student-mcp` command line.

student-mcp serve                      # Streamable HTTP on :8102, Bearer token required
student-mcp serve --stdio --as sv001   # dev only: single user over stdio
student-mcp issue-token sv001          # print a session token for a demo account (password: demo)
student-mcp accounts                   # list demo accounts and their personas
"""

import argparse
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from co5151_contracts.env import find_env_file, load_env_file

from .auth import AuthError, TokenSigner, login
from .config import Settings
from .db import StudentDB


def _issue(settings: Settings, username: str, password: str) -> str:
    db = StudentDB(settings.db_path, settings.data_dir)
    return login(db, TokenSigner(settings.token_secret, settings.token_ttl), username, password)


def cmd_serve(a, settings: Settings) -> int:
    from .server import serve  # imports the MCP SDK only when serving

    settings = replace(settings, host=a.host or settings.host, port=a.port or settings.port)
    if not a.stdio:
        serve(settings, "http")
        return 0
    token = os.environ.get("STUDENT_MCP_SESSION_TOKEN")
    if a.as_user:
        token = _issue(settings, a.as_user, a.password)
    if not token:
        print("stdio mode needs --as <username> or STUDENT_MCP_SESSION_TOKEN", file=sys.stderr)
        return 2
    serve(settings, "stdio", stdio_token=token)
    return 0


def cmd_issue_token(a, settings: Settings) -> int:
    try:
        print(_issue(settings, a.username, a.password))
    except AuthError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_accounts(a, settings: Settings) -> int:
    db = StudentDB(settings.db_path, settings.data_dir)
    for r in db.conn.execute("SELECT username, role, mssv, advisees, persona FROM accounts ORDER BY username"):
        who = r["mssv"] or f"advisees={r['advisees']}"
        print(f"{r['username']:<8} {r['role']:<8} {who:<45} {r['persona'] or ''}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="student-mcp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--env-file", type=Path, help="default: nearest .env up to the repo root")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the MCP server")
    s.add_argument("--stdio", action="store_true", help="dev only: single user over stdio")
    s.add_argument("--as", dest="as_user", metavar="USERNAME", help="stdio: log in as this demo account")
    s.add_argument("--password", default="demo")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=cmd_serve)

    t = sub.add_parser("issue-token", help="print a session token for a demo account")
    t.add_argument("username")
    t.add_argument("--password", default="demo")
    t.set_defaults(fn=cmd_issue_token)

    sub.add_parser("accounts", help="list demo accounts").set_defaults(fn=cmd_accounts)

    a = ap.parse_args(argv)
    load_env_file(a.env_file or find_env_file())
    logging.basicConfig(level=os.environ.get("STUDENT_MCP_LOG_LEVEL", "INFO"), stream=sys.stderr)
    return a.fn(a, Settings.from_env())


if __name__ == "__main__":
    sys.exit(main())
