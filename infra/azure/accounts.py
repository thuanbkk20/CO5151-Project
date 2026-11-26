"""Write the deployment's account file: the demo accounts of student-server with one private password.

Run on the VM by deploy.sh with the app's Python; the password comes on stdin so it never shows in `ps`:

    printf %s "$PASSWORD" | .venv/bin/python accounts.py /opt/co5151/accounts.json
"""

import json
import os
import sys
from pathlib import Path

from co5151_backend.infrastructure.identity import default_accounts_file
from co5151_contracts.security import hash_password

MIN_LENGTH = 12


def main(out: Path, password: str) -> None:
    if len(password) < MIN_LENGTH or password == "demo":
        sys.exit(f"accounts: the password needs at least {MIN_LENGTH} characters")
    rows = json.loads(default_accounts_file().read_text("utf-8"))
    for row in rows:
        row["password_hash"] = hash_password(password)
    os.umask(0o077)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(out)
    print(f"accounts: {len(rows)} accounts -> {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.stdin.read().strip().strip("'\""))
