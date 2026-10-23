"""`co5151-eval` command line.

co5151-eval run --agent co5151_eval.baselines:record_template --seeds 0 1 2
co5151-eval run --agent my_pkg.adapter:make_agent --only P01,O02
co5151-eval check-gold
co5151-eval security [--url http://127.0.0.1:8102/mcp]
"""

import argparse
import importlib
import sys
import time
from pathlib import Path

from .gold import check_gold
from .runner import run, write_report
from .tasks import load_tasks

DEFAULT_OUT = Path("eval/results")


def load_factory(spec: str):
    """'package.module:attr' → the agent factory."""
    module, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit(f"--agent must look like package.module:factory, got {spec!r}")
    return getattr(importlib.import_module(module), attr)


def _select(tasks, only: str | None, groups: list[str] | None):
    if only:
        wanted = set(only.split(","))
        unknown = wanted - {t.id for t in tasks}
        if unknown:
            raise SystemExit(f"unknown task ids: {sorted(unknown)}")
        tasks = [t for t in tasks if t.id in wanted]
    if groups:
        tasks = [t for t in tasks if t.group.value in groups]
    return tasks


def cmd_run(a) -> int:
    factory = load_factory(a.agent)
    tasks = _select(load_tasks(a.tasks), a.only, a.group)
    name = a.agent.rpartition(":")[2]
    out = a.out or DEFAULT_OUT / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}"

    def progress(r):
        mark = "ERR " if r.error else {True: "PASS", False: "fail", None: "hand"}[r.passed]
        print(f"  [seed {r.seed}] {r.task_id} {mark} {r.outcome:<7} {r.latency_s:.2f}s", file=sys.stderr)

    records = run(factory, tasks, a.seeds, on_record=progress if a.verbose else None)
    meta = {"agent": a.agent, "tasks": len(tasks), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    summary = write_report(records, out, f"Kết quả: {name}", meta)
    print((out / "summary.md").read_text("utf-8"))
    print(f"Chi tiết: {out}/results.jsonl", file=sys.stderr)
    return 0 if summary["overall"]["errors"] == 0 else 1


def cmd_check_gold(a) -> int:
    problems = check_gold(load_tasks(a.tasks))
    for p in problems:
        print(p)
    print("gold facts OK" if not problems else f"{len(problems)} mismatches", file=sys.stderr)
    return 1 if problems else 0


def cmd_security(a) -> int:
    from . import security

    results = security.run_suite(a.url)
    print(security.to_markdown(results))
    if a.json:
        a.json.write_text(security.to_json(results), "utf-8")
    return 0 if all(r.passed for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="co5151-eval")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="chạy một hệ thống trên tập task và ghi báo cáo")
    r.add_argument("--agent", required=True, help="package.module:factory, factory(seed) -> Agent")
    r.add_argument("--tasks", help="file JSON task (mặc định: bộ 24 câu đi kèm)")
    r.add_argument("--seeds", type=int, nargs="+", default=[0])
    r.add_argument("--only", help="danh sách id, ví dụ P01,O02")
    r.add_argument("--group", nargs="+", choices=["basic", "personal", "missing_info", "out_of_scope"])
    r.add_argument("--out", type=Path, help=f"thư mục kết quả (mặc định {DEFAULT_OUT}/<thời gian>-<agent>)")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)

    g = sub.add_parser("check-gold", help="đối chiếu đáp án facts với mock data của Student Record MCP")
    g.add_argument("--tasks")
    g.set_defaults(fn=cmd_check_gold)

    s = sub.add_parser("security", help="kiểm thử tấn công tầng tool vào Student Record MCP qua HTTP")
    s.add_argument("--url", help="server đang chạy (cần STUDENT_MCP_TOKEN_SECRET trùng); mặc định tự dựng server local")
    s.add_argument("--json", type=Path, help="ghi thêm kết quả dạng JSON")
    s.set_defaults(fn=cmd_security)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
