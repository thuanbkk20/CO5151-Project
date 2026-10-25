import json
import time
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path

from .tasks import SUITES, Group, Task, load_tasks

TEMPLATE_TOKENS = 100

METRICS = [
    ("pass_rate", "Pass", "max"),
    ("needs_human", "Chấm tay", None),
    ("outcome_accuracy", "Đúng kết cục", "max"),
    ("strict_refusal_rate", "Từ chối đúng (bẫy)", "max"),
    ("false_refusal_rate", "Từ chối nhầm", "min"),
    ("clarification_rate", "Hỏi lại khi thiếu thông tin", "max"),
    ("fact_recall", "Fact recall", "max"),
    ("citation_recall", "Citation recall", "max"),
    ("leaks", "Leak", "min"),
    ("errors", "Lỗi", "min"),
    ("latency_p50_s", "Độ trễ p50 (s)", "min"),
    ("latency_p95_s", "Độ trễ p95 (s)", "min"),
    ("tokens_mean", "Token/câu", "min"),
]

GROUP_LABELS = {
    Group.BASIC.value: "Cơ bản",
    Group.PERSONAL.value: "Cá nhân",
    Group.MISSING_INFO.value: "Thiếu thông tin",
    Group.OUT_OF_SCOPE.value: "Bẫy / ngoài phạm vi",
}

PALETTE = ["#4269d0", "#efb118", "#ff725c", "#6cc5b0", "#a463f2"]


@dataclass
class Run:
    name: str
    summary: dict
    records: list[dict]

    @property
    def uses_llm(self) -> bool:
        config = self.summary.get("agent_config") or {}
        return bool(config.get("llm"))


def load_run(directory: Path) -> Run:
    directory = Path(directory)
    summary = json.loads((directory / "summary.json").read_text("utf-8"))
    lines = (directory / "results.jsonl").read_text("utf-8").splitlines()
    return Run(directory.name, summary, [json.loads(line) for line in lines if line.strip()])


def _all_tasks() -> dict[str, Task]:
    return {t.id: t for suite in SUITES for t in load_tasks(suite=suite)}


def _fmt(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _best(values: list, direction: str | None) -> set[int]:
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    if direction is None or len(present) < 2:
        return set()
    target = (max if direction == "max" else min)(v for _, v in present)
    winners = {i for i, v in present if v == target}
    return winners if len(winners) < len(present) else set()


def _config_text(run: Run) -> str:
    config = run.summary.get("agent_config")
    if not config:
        return "không dùng LLM"
    llm = config.get("llm") or {}
    parts = [f"{llm.get('provider', '?')}/{llm.get('model', '?')}"] if llm else []
    parts += [f"{k}: {v}" for k, v in config.items() if k != "llm"]
    return ", ".join(parts)


def _runs_section(runs: list[Run]) -> str:
    rows = "".join(
        f"<tr><td><span class='swatch' style='background:{PALETTE[i % len(PALETTE)]}'></span>{escape(r.name)}</td>"
        f"<td><code>{escape(r.summary.get('agent', ''))}</code></td><td>{escape(_config_text(r))}</td>"
        f"<td>{len(r.summary.get('seeds', []))}</td><td>{r.summary.get('tasks', '')}</td>"
        f"<td><code>{escape(r.summary.get('commit') or 'không rõ')}</code></td>"
        f"<td>{escape(r.summary.get('started', ''))}</td></tr>"
        for i, r in enumerate(runs)
    )
    return (
        "<table><thead><tr><th>Cấu hình</th><th>Agent</th><th>LLM / thành phần</th><th>Seed</th><th>Câu</th>"
        f"<th>Commit</th><th>Bắt đầu</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _metric_table(blocks: list[dict], runs: list[Run]) -> str:
    head = "".join(f"<th class='num'>{escape(r.name)}</th>" for r in runs)
    body = []
    for key, label, direction in METRICS:
        values = [b.get(key) for b in blocks]
        best = _best(values, direction)
        cells = "".join(f"<td class='num{' best' if i in best else ''}'>{_fmt(v)}</td>" for i, v in enumerate(values))
        hint = {"max": " ↑", "min": " ↓"}.get(direction or "", "")
        body.append(f"<tr><td>{escape(label)}<span class='hint'>{hint}</span></td>{cells}</tr>")
    return f"<table><thead><tr><th>Chỉ số</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _seed_line(runs: list[Run]) -> str:
    items = []
    for r in runs:
        s = r.summary
        per_seed = ", ".join(_fmt(v) for v in s.get("pass_rate_by_seed", []))
        items.append(
            f"<li><b>{escape(r.name)}</b>: Pass {_fmt(s.get('pass_rate_mean'))} ± {_fmt(s.get('pass_rate_std'))}"
            f" (theo seed: {per_seed})</li>"
        )
    return f"<ul class='seeds'>{''.join(items)}</ul>"


def _bar_chart(runs: list[Run]) -> str:
    groups = list(GROUP_LABELS)
    width, height, left, bottom, top = 720, 260, 40, 40, 16
    plot_w, plot_h = width - left - 10, height - bottom - top
    slot = plot_w / len(groups)
    bar = min(36, (slot - 16) / max(len(runs), 1))
    parts = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Pass theo nhóm'>"]
    for tick in (0, 0.25, 0.5, 0.75, 1):
        y = top + plot_h * (1 - tick)
        parts.append(f"<line x1='{left}' x2='{width - 10}' y1='{y}' y2='{y}' class='grid'/>")
        parts.append(f"<text x='{left - 6}' y='{y + 4}' class='axis' text-anchor='end'>{tick:.2f}</text>")
    for gi, group in enumerate(groups):
        x0 = left + gi * slot + (slot - bar * len(runs)) / 2
        for ri, run in enumerate(runs):
            value = run.summary["by_group"].get(group, {}).get("pass_rate")
            x = x0 + ri * bar
            if value is None:
                y = top + plot_h - 4
                parts.append(f"<text x='{x + bar / 2}' y='{y}' class='axis' text-anchor='middle'>–</text>")
                continue
            h = plot_h * value
            color = PALETTE[ri % len(PALETTE)]
            parts.append(
                f"<rect x='{x + 1}' y='{top + plot_h - h}' width='{bar - 2}' height='{h}' rx='2' fill='{color}'>"
                f"<title>{escape(run.name)} · {escape(GROUP_LABELS[group])}: {value:.2f}</title></rect>"
            )
            parts.append(
                f"<text x='{x + bar / 2}' y='{top + plot_h - h - 4}' class='value' text-anchor='middle'>"
                f"{value:.2f}</text>"
            )
        label_x = left + gi * slot + slot / 2
        parts.append(
            f"<text x='{label_x}' y='{height - 14}' class='axis' text-anchor='middle'>"
            f"{escape(GROUP_LABELS[group])}</text>"
        )
    parts.append("</svg>")
    legend = "".join(
        f"<span><i style='background:{PALETTE[i % len(PALETTE)]}'></i>{escape(r.name)}</span>"
        for i, r in enumerate(runs)
    )
    return f"<div class='legend'>{legend}</div>{''.join(parts)}"


def _verdict(records: list[dict]) -> tuple[str, str]:
    if not records:
        return "na", "–"
    if any(r["error"] for r in records):
        return "fail", "lỗi"
    passed = [r["passed"] for r in records]
    if all(p is None for p in passed):
        return "hand", "chấm tay"
    ok = sum(p is True for p in passed)
    css = "pass" if ok == len(passed) else "fail" if ok == 0 else "mixed"
    return css, f"{ok}/{len(passed)}"


def _record_detail(record: dict, uses_llm: bool) -> str:
    flags = []
    if record["error"]:
        flags.append(f"<span class='flag bad'>lỗi: {escape(record['error'])}</span>")
    if uses_llm and record["tokens"] == TEMPLATE_TOKENS:
        flags.append("<span class='flag bad'>nghi trả lời bằng template</span>")
    if record["forbidden_hits"]:
        hits = ", ".join(f"<code>{escape(h)}</code>" for h in record["forbidden_hits"])
        flags.append(f"<span class='flag bad'>khớp mẫu cấm: {hits}</span>")
    facts = f"{record['facts_hit']}/{record['facts_total']}" if record["facts_total"] else "–"
    meta = (
        f"seed {record['seed']} · kết cục <b>{escape(record['outcome'])}</b> · fact {facts} · "
        f"{record['latency_s']:.2f} s · {record['tokens']} token · tool: "
        f"{escape(', '.join(record['tool_calls']) or 'không')}"
    )
    body = f"<pre>{escape(record['text'])}</pre>"
    return f"<div class='answer'><div class='meta'>{meta} {' '.join(flags)}</div>{body}</div>"


def _task_table(runs: list[Run], tasks: dict[str, Task]) -> str:
    by_run = [defaultdict(list) for _ in runs]
    for index, run in enumerate(runs):
        for record in run.records:
            by_run[index][record["task_id"]].append(record)
    order = [tid for tid in tasks if any(tid in b for b in by_run)]
    order += sorted({tid for b in by_run for tid in b} - set(order))
    head = "".join(f"<th>{escape(r.name)}</th>" for r in runs)
    rows = []
    for tid in order:
        task = tasks.get(tid)
        question = escape(task.question) if task else ""
        expected = escape(task.expected.value) if task else ""
        cells, details = [], []
        for index, run in enumerate(runs):
            records = sorted(by_run[index].get(tid, []), key=lambda r: r["seed"])
            css, label = _verdict(records)
            suspicious = run.uses_llm and any(r["tokens"] == TEMPLATE_TOKENS for r in records)
            leak = any(r["forbidden_hits"] for r in records)
            marks = ("⚠" if suspicious else "") + ("●" if leak else "")
            cells.append(f"<td><span class='badge {css}'>{label}</span>{marks}</td>")
            if records:
                answers = "".join(_record_detail(r, run.uses_llm) for r in records)
                details.append(f"<h4>{escape(run.name)}</h4>{answers}")
        reference = ""
        if task and task.reference_answer:
            reference = f"<p class='ref'><b>Đáp án mẫu:</b> {escape(task.reference_answer)}</p>"
        group = GROUP_LABELS.get(task.group.value, "") if task else ""
        rows.append(
            f"<tr><td><b>{escape(tid)}</b></td><td>{escape(group)}</td>"
            f"<td>{expected}</td>{''.join(cells)}<td><details><summary>{question}</summary>{reference}"
            f"{''.join(details)}</details></td></tr>"
        )
    return (
        f"<table class='tasks'><thead><tr><th>Câu</th><th>Nhóm</th><th>Kỳ vọng</th>{head}"
        f"<th>Câu hỏi (bấm để xem câu trả lời)</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _warnings(runs: list[Run]) -> str:
    notes = []
    for run in runs:
        suspicious = sum(1 for r in run.records if run.uses_llm and r["tokens"] == TEMPLATE_TOKENS)
        if suspicious:
            notes.append(
                f"<b>{escape(run.name)}</b>: {suspicious} câu có {TEMPLATE_TOKENS} token, nghi Advisor đã trả lời bằng "
                "template thay vì LLM (LLM lỗi hoặc hết quota). Chạy lại các câu này trước khi dùng số liệu."
            )
        leaks = sum(1 for r in run.records if r["forbidden_hits"])
        if leaks:
            notes.append(
                f"<b>{escape(run.name)}</b>: {leaks} câu khớp mẫu cấm (đánh dấu ●). Mẫu cấm là regex, có thể bắt nhầm "
                "câu phủ định; đọc lại từng câu trước khi kết luận là rò rỉ."
            )
    if not notes:
        return "<p class='ok'>Không có câu nghi trả lời bằng template và không có câu khớp mẫu cấm.</p>"
    return "<ul class='warn'>" + "".join(f"<li>{n}</li>" for n in notes) + "</ul>"


STYLE = """
:root { --bg:#fbfbfa; --fg:#1f2328; --muted:#656d76; --line:#d8dee4; --card:#ffffff;
  --pass:#1a7f37; --pass-bg:#dafbe1; --fail:#cf222e; --fail-bg:#ffebe9; --mixed:#9a6700; --mixed-bg:#fff8c5;
  --hand:#57606a; --hand-bg:#eaeef2; --best:#dafbe1; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --fg:#e6edf3; --muted:#8d96a0; --line:#30363d;
  --card:#161b22; --pass:#3fb950; --pass-bg:#12261e; --fail:#f85149; --fail-bg:#2d1214; --mixed:#d29922;
  --mixed-bg:#2b2111; --hand:#8d96a0; --hand-bg:#21262d; --best:#12261e; } }
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px 64px; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:19px; margin:32px 0 10px; } h4 { margin:14px 0 4px; }
.sub { color:var(--muted); margin:0 0 16px; }
table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line);
  border-radius:8px; overflow:hidden; display:block; overflow-x:auto; }
th, td { padding:7px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
th { font-size:13px; color:var(--muted); font-weight:600; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
td.best { background:var(--best); font-weight:600; }
.hint { color:var(--muted); font-size:12px; }
.badge { display:inline-block; min-width:62px; text-align:center; padding:1px 8px; border-radius:10px;
  font-size:13px; font-weight:600; margin-right:4px; }
.badge.pass { color:var(--pass); background:var(--pass-bg); }
.badge.fail { color:var(--fail); background:var(--fail-bg); }
.badge.mixed { color:var(--mixed); background:var(--mixed-bg); }
.badge.hand, .badge.na { color:var(--hand); background:var(--hand-bg); }
details summary { cursor:pointer; } .tasks td:last-child { min-width:320px; }
.answer { border-left:3px solid var(--line); padding:4px 0 4px 10px; margin:8px 0; }
.answer pre { white-space:pre-wrap; font-family:inherit; font-size:13px; line-height:1.45; margin:6px 0 0;
  max-height:320px; overflow:auto; }
.meta { font-size:12.5px; color:var(--muted); } .flag { margin-left:6px; font-size:12px; }
.flag.bad { color:var(--fail); } .ref { font-size:13px; color:var(--muted); }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:13px; margin-bottom:4px; }
.legend i, .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; }
svg { width:100%; height:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; }
svg .grid { stroke:var(--line); } svg .axis { fill:var(--muted); font-size:12px; }
svg .value { fill:var(--fg); font-size:11px; }
.warn li { margin:4px 0; } .ok { color:var(--pass); } .seeds { margin:8px 0 0; padding-left:20px; }
code { font-size:12.5px; }
"""


def render(runs: list[Run], title: str = "Kết quả đánh giá Advisor") -> str:
    tasks = _all_tasks()
    groups = "".join(
        f"<h4>{escape(GROUP_LABELS[g])}</h4>{_metric_table([r.summary['by_group'].get(g, {}) for r in runs], runs)}"
        for g in GROUP_LABELS
    )
    generated = time.strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{STYLE}</style></head>
<body><main>
<h1>{escape(title)}</h1>
<p class="sub">Tạo lúc {generated} bằng <code>co5151-eval report</code>.
↑ cao hơn là tốt, ↓ thấp hơn là tốt; ô tô xanh là tốt nhất.</p>
<h2>Các cấu hình</h2>{_runs_section(runs)}
<h2>Cần kiểm tra</h2>{_warnings(runs)}
<h2>So sánh tổng</h2>{_metric_table([r.summary["overall"] for r in runs], runs)}{_seed_line(runs)}
<h2>Pass theo nhóm câu hỏi</h2>{_bar_chart(runs)}
<h2>Từng câu</h2>
<p class="sub">Ô là số seed đạt / tổng seed. ⚠ nghi trả lời bằng template, ● khớp mẫu cấm.
Bấm câu hỏi để xem câu trả lời.</p>
{_task_table(runs, tasks)}
<h2>Chi tiết theo nhóm</h2>{groups}
</main></body></html>
"""


def write_html_report(directories: list[Path], out: Path, title: str = "Kết quả đánh giá Advisor") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render([load_run(d) for d in directories], title), "utf-8")
    return out
