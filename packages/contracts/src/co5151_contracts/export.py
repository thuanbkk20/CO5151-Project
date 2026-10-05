"""Export the contracts as JSON Schema files for non-Python consumers.

uv run python -m co5151_contracts.export           # (re)generate packages/contracts/schemas/
uv run python -m co5151_contracts.export --check   # fail if the committed files are stale
"""

import argparse
import json
import sys
from pathlib import Path

from .auth import SessionClaims
from .envelope import ToolErrorBody
from .tools import STUDENT_RECORD_TOOLS

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "schemas"


def render() -> dict[str, str]:
    files = {
        "common/tool-error.json": ToolErrorBody.model_json_schema(),
        "common/session-claims.json": SessionClaims.model_json_schema(),
        "student-record/tools.json": [t.manifest() for t in STUDENT_RECORD_TOOLS.values()],
    }
    for t in STUDENT_RECORD_TOOLS.values():
        files[f"student-record/{t.name}.input.json"] = t.input_schema()
        files[f"student-record/{t.name}.output.json"] = t.output_schema()
    return {path: json.dumps(doc, ensure_ascii=False, indent=2) + "\n" for path, doc in files.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="verify instead of writing")
    a = ap.parse_args(argv)

    rendered = render()
    if a.check:
        stale = [
            p for p, text in rendered.items() if not (a.out / p).is_file() or (a.out / p).read_text("utf-8") != text
        ]
        extra = sorted(
            str(f.relative_to(a.out)) for f in a.out.rglob("*.json") if str(f.relative_to(a.out)) not in rendered
        )
        for p in stale + extra:
            print(f"stale: {p}", file=sys.stderr)
        return 1 if stale or extra else 0

    for p, text in rendered.items():
        (a.out / p).parent.mkdir(parents=True, exist_ok=True)
        (a.out / p).write_text(text, "utf-8")
    print(f"wrote {len(rendered)} schema files to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
