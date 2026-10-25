import argparse
import importlib
import subprocess
import sys
import time
from pathlib import Path

from co5151_contracts.env import find_env_file, load_env_file

from .gold import check_gold
from .html_report import write_html_report
from .runner import run, write_report
from .tasks import load_tasks

DEFAULT_OUT = Path("eval/results")


def load_factory(spec: str):
    module, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit(f"--agent must look like package.module:factory, got {spec!r}")
    return getattr(importlib.import_module(module), attr)


def git_commit() -> str | None:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return sha.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


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
    tasks = _select(load_tasks(a.tasks, a.suite), a.only, a.group)
    name = a.agent.rpartition(":")[2]
    out = a.out or DEFAULT_OUT / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}"

    def progress(r):
        mark = "ERR " if r.error else {True: "PASS", False: "fail", None: "hand"}[r.passed]
        print(f"  [seed {r.seed}] {r.task_id} {mark} {r.outcome:<7} {r.latency_s:.2f}s", file=sys.stderr)

    probe = factory(a.seeds[0])
    config = probe.describe() if callable(getattr(probe, "describe", None)) else None
    records = run(factory, tasks, a.seeds, on_record=progress if a.verbose else None)
    meta = {"agent": a.agent, "agent_config": config, "tasks": len(tasks), "commit": git_commit(),
            "started": time.strftime("%Y-%m-%d %H:%M:%S")}  # fmt: skip
    summary = write_report(records, out, f"Kết quả: {name}", meta)
    write_html_report([out], out / "report.html", f"Kết quả: {name}")
    print((out / "summary.md").read_text("utf-8"))
    print(f"Chi tiết: {out}/results.jsonl · {out}/report.html", file=sys.stderr)
    return 0 if summary["overall"]["errors"] == 0 else 1


def cmd_report(a) -> int:
    out = a.out or a.runs[0].parent / "report.html"
    write_html_report(a.runs, out, a.title)
    print(out)
    return 0


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
    p.add_argument("--env-file", type=Path, help="mặc định: file .env gần nhất, tìm ngược lên tới gốc repo")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="chạy một hệ thống trên tập task và ghi báo cáo")
    r.add_argument("--agent", required=True, help="package.module:factory, factory(seed) -> Agent")
    r.add_argument("--suite", choices=["tasks", "injection"], default="tasks",
                   help="bộ đi kèm: 24 câu đánh giá hoặc 12 ca prompt injection")  # fmt: skip
    r.add_argument("--tasks", help="file JSON task riêng (thay cho --suite)")
    r.add_argument("--seeds", type=int, nargs="+", default=[0])
    r.add_argument("--only", help="danh sách id, ví dụ P01,O02")
    r.add_argument("--group", nargs="+", choices=["basic", "personal", "missing_info", "out_of_scope"])
    r.add_argument("--out", type=Path, help=f"thư mục kết quả (mặc định {DEFAULT_OUT}/<thời gian>-<agent>)")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)

    rp = sub.add_parser("report", help="gộp một hoặc nhiều thư mục kết quả thành một trang HTML để so sánh")
    rp.add_argument("runs", type=Path, nargs="+", help="thư mục kết quả của lệnh run")
    rp.add_argument("-o", "--out", type=Path, help="file HTML (mặc định report.html cạnh thư mục đầu tiên)")
    rp.add_argument("--title", default="Kết quả đánh giá Advisor")
    rp.set_defaults(fn=cmd_report)

    g = sub.add_parser("check-gold", help="đối chiếu đáp án facts với mock data của Student Record MCP")
    g.add_argument("--tasks")
    g.set_defaults(fn=cmd_check_gold)

    s = sub.add_parser("security", help="kiểm thử tấn công tầng tool vào Student Record MCP qua HTTP")
    s.add_argument("--url", help="server đang chạy (cần STUDENT_MCP_TOKEN_SECRET trùng); mặc định tự dựng server local")
    s.add_argument("--json", type=Path, help="ghi thêm kết quả dạng JSON")
    s.set_defaults(fn=cmd_security)

    a = p.parse_args(argv)
    load_env_file(a.env_file or find_env_file())
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
