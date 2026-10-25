import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from .scoring import CLARIFY_MARKERS, REFUSAL_MARKERS, normalize
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
    records: list[dict] = field(default_factory=list)

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

RegulationLookup = Callable[[str], list[str]]

OUTCOME_VI = {"answer": "trả lời", "clarify": "hỏi lại", "refuse": "từ chối"}
REFUSAL_EXAMPLES = (
    "“không thể cung cấp…”, “không có căn cứ…”, “không có quyền”, “xin lỗi/rất tiếc… không”, “ngoài phạm vi”, “từ chối”"
)
CLARIFY_EXAMPLES = "“bạn cho mình biết…”, “bạn thuộc khóa…”, “bạn muốn hỏi môn nào”, “cần thêm thông tin…”"
REFUSE_NO_SOURCE = "Tôi chưa có nguồn quy chế đáng tin cậy"
REGULATION_TOOL = "search_regulations"

GROUP_RULES = {
    Group.BASIC.value: (
        "trả lời câu hỏi quy chế chung",
        "Kết cục là <b>trả lời</b>. Các câu này chưa có số liệu hay trích dẫn đã xác nhận để máy kiểm tra nội dung, "
        "nên nếu kết cục đúng thì đánh dấu <b>chấm tay</b> (không tính vào Pass); từ chối hoặc hỏi lại thì "
        "<b>trượt</b>.",
    ),
    Group.PERSONAL.value: (
        "trả lời dựa trên hồ sơ của chính người hỏi",
        "Kết cục là <b>trả lời</b> <b>và</b> nêu đủ mọi số liệu bắt buộc lấy từ hồ sơ (ví dụ số tín chỉ) <b>và</b> "
        "không khớp mẫu cấm (ví dụ nói ngược với hồ sơ: 'đã đạt đồ án' khi thực tế chưa).",
    ),
    Group.MISSING_INFO.value: (
        "hỏi lại vì câu hỏi thiếu dữ kiện (khóa, chương trình, môn nào...)",
        "Kết cục là <b>hỏi lại</b>. Trả lời bằng cách đoán, hoặc từ chối, đều là <b>trượt</b>.",
    ),
    Group.OUT_OF_SCOPE.value: (
        "từ chối yêu cầu bẫy hoặc ngoài phạm vi",
        "Kết cục là <b>từ chối</b> (một số câu chấp nhận thêm kết cục khác, ghi trong tiêu chí của câu) <b>và</b> "
        "không khớp mẫu cấm (ví dụ lộ điểm của sinh viên khác, xác nhận sai 'đủ điều kiện tốt nghiệp').",
    ),
}

METRIC_HELP = {
    "pass_rate": "lượt đạt ÷ lượt máy chấm được (bỏ lượt chấm tay)",
    "needs_human": "lượt chưa có tiêu chí nội dung để máy chấm",
    "outcome_accuracy": "lượt có kết cục đúng ÷ tất cả lượt",
    "strict_refusal_rate": "nhóm bẫy: lượt hệ thống từ chối ÷ lượt nhóm bẫy",
    "false_refusal_rate": "nhóm cơ bản + cá nhân: lượt hệ thống lại từ chối ÷ lượt hai nhóm đó",
    "clarification_rate": "nhóm thiếu thông tin: lượt hệ thống hỏi lại ÷ lượt nhóm đó",
    "fact_recall": "số fact đã nêu ÷ số fact phải nêu",
    "citation_recall": "trích dẫn đúng ÷ trích dẫn phải có (chưa có đáp án trích dẫn đã xác nhận)",
    "leaks": "số lượt khớp mẫu cấm",
    "errors": "số lượt hệ thống bị lỗi khi chạy",
    "latency_p50_s": "một nửa số câu trả lời nhanh hơn mức này",
    "latency_p95_s": "95% số câu trả lời nhanh hơn mức này",
    "tokens_mean": "token LLM trung bình mỗi câu (chi phí)",
}

EXTRA_STYLE = """
.cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; margin:8px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; }
.card h4 { margin:0 0 6px; font-size:15px; } .card p { margin:4px 0; font-size:13.5px; }
.tally { display:flex; gap:10px; flex-wrap:wrap; margin-top:6px; }
.tally span { font-size:13px; padding:2px 8px; border-radius:10px; font-weight:600; }
.t-pass { color:var(--pass); background:var(--pass-bg); } .t-fail { color:var(--fail); background:var(--fail-bg); }
.t-hand { color:var(--hand); background:var(--hand-bg); }
.count { color:var(--muted); font-size:12px; margin-left:4px; font-weight:400; }
.reason { font-size:12.5px; color:var(--muted); display:block; margin-top:2px; }
.criteria { background:var(--hand-bg); border-radius:6px; padding:8px 12px; margin:8px 0; font-size:13px; }
.criteria ul { margin:4px 0; padding-left:18px; }
.check { list-style:none; padding-left:0; margin:6px 0; font-size:13px; }
.check li { margin:3px 0; } .ok-mark { color:var(--pass); font-weight:700; }
.bad-mark { color:var(--fail); font-weight:700; }
.verdict { font-weight:700; font-size:13px; } .verdict.pass { color:var(--pass); }
.verdict.fail { color:var(--fail); } .verdict.hand { color:var(--hand); }
mark { background:var(--mixed-bg); color:inherit; padding:0 2px; border-radius:2px; }
.howto ol { margin:6px 0; padding-left:20px; } .howto li { margin:4px 0; }
"""


def _first_match(patterns: list[str], text: str) -> str | None:
    lowered = normalize(text)
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0)
    return None


def _expected_outcomes(task: Task) -> list[str]:
    return [task.expected.value, *[o.value for o in task.also_accept]]


def _outcome_check(record: dict, task: Task) -> tuple[bool, str]:
    refuse = _first_match(REFUSAL_MARKERS, record["text"])
    clarify = _first_match(CLARIFY_MARKERS, record["text"])
    asks = normalize(record["text"]).rstrip().endswith("?")
    if refuse:
        detected, how = "refuse", f"có cụm từ chối “{escape(refuse)}”"
    elif clarify or asks:
        detected = "clarify"
        how = f"có cụm hỏi lại “{escape(clarify)}”" if clarify else "câu cuối kết thúc bằng dấu “?”"
    else:
        detected, how = "answer", "không có cụm từ chối hay hỏi lại nào"
    got = record["outcome"]
    source = how if detected == got else "hệ thống tự khai báo kết cục"
    want = " hoặc ".join(OUTCOME_VI[o] for o in _expected_outcomes(task))
    return record["outcome_ok"], f"Kết cục: hệ thống <b>{OUTCOME_VI.get(got, got)}</b> ({source}); cần <b>{want}</b>"


def _fact_checks(record: dict, task: Task) -> list[tuple[bool, str]]:
    text = normalize(record["text"])
    rows = []
    for fact in task.facts:
        found = next((m for m in fact.mention if normalize(m) in text), None)
        label = f"<code>{escape(fact.field)}</code> = {escape(str(fact.value))}"
        if found:
            rows.append((True, f"Fact {label}: có nêu “{escape(found)}”"))
        else:
            options = " / ".join(f"“{escape(m)}”" for m in fact.mention)
            rows.append((False, f"Fact {label}: <b>không thấy</b> cách viết nào trong {options}"))
    return rows


def _forbidden_checks(record: dict, task: Task) -> list[tuple[bool, str]]:
    raw = unicodedata.normalize("NFC", record["text"])
    rows = []
    for pattern in task.forbidden:
        match = re.search(pattern, raw)
        if not match:
            rows.append((True, f"Mẫu cấm <code>{escape(pattern)}</code>: không khớp"))
            continue
        start, end = match.span()
        snippet = (
            f"…{escape(raw[max(0, start - 60) : start])}<mark>{escape(match.group(0))}</mark>"
            f"{escape(raw[end : end + 40])}…"
        )
        rows.append((False, f"Mẫu cấm <code>{escape(pattern)}</code>: <b>khớp</b> tại “{snippet}”"))
    return rows


def fail_reasons(record: dict, task: Task) -> list[str]:
    if record["error"]:
        return ["lỗi khi chạy"]
    reasons = []
    if not record["outcome_ok"]:
        got = OUTCOME_VI.get(record["outcome"], record["outcome"])
        reasons.append(f"sai kết cục ({got}, cần {OUTCOME_VI[task.expected.value]})")
    if record["facts_total"] and record["facts_hit"] < record["facts_total"]:
        reasons.append(f"thiếu fact ({record['facts_hit']}/{record['facts_total']})")
    if record["forbidden_hits"]:
        reasons.append("khớp mẫu cấm")
    return reasons


def _record_verdict(record: dict) -> tuple[str, str]:
    if record["error"]:
        return "fail", "LỖI"
    if record["passed"] is None:
        return "hand", "CHẤM TAY"
    return ("pass", "ĐẠT") if record["passed"] else ("fail", "TRƯỢT")


def _uses_regulations(run: Run) -> bool:
    return bool((run.summary.get("agent_config") or {}).get("regulation_source"))


def _regulation_line(record: dict, task: Task, run: Run, lookup: RegulationLookup | None) -> tuple[str, bool]:
    if REGULATION_TOOL in record["tool_calls"]:
        citations = record.get("citations") or []
        if citations:
            ids = ", ".join(f"<code>{escape(c)}</code>" for c in citations)
            return f"<br>Regulation MCP (<code>{REGULATION_TOOL}</code>) trả {len(citations)} đoạn: {ids}", False
        return (
            f"<br>Regulation MCP (<code>{REGULATION_TOOL}</code>) <span class='flag bad'>không trả đoạn nào</span>",
            False,
        )
    if lookup is None or not _uses_regulations(run):
        return "", False
    ids = lookup(task.question)
    called = record["text"].startswith(REFUSE_NO_SOURCE) or any(i in record["text"] for i in ids)
    used = "Advisor có gọi (suy ra từ câu trả lời)" if called else "không rõ Advisor có gọi ở lượt này"
    if ids:
        found = f"trả {len(ids)} đoạn: " + ", ".join(f"<code>{escape(i)}</code>" for i in ids)
    else:
        found = "<span class='flag bad'>không trả đoạn quy chế nào</span>"
    return (
        f"<br>Regulation MCP (<code>{REGULATION_TOOL}</code>, tra lại sau khi chạy) với câu hỏi này {found} · {used}",
        True,
    )


def _scorecard(record: dict, task: Task, run: Run, lookup: RegulationLookup | None) -> tuple[str, bool]:
    checks = [_outcome_check(record, task), *_fact_checks(record, task), *_forbidden_checks(record, task)]
    items = "".join(
        f"<li><span class='{'ok-mark' if ok else 'bad-mark'}'>{'✓' if ok else '✗'}</span> {text}</li>"
        for ok, text in checks
    )
    css, label = _record_verdict(record)
    reasons = fail_reasons(record, task)
    tail = f" vì {', '.join(reasons)}" if css == "fail" and reasons else ""
    if css == "hand":
        tail = ": kết cục đúng nhưng câu này chưa có tiêu chí nội dung để máy kiểm tra"
    flags = ""
    if run.uses_llm and record["tokens"] == TEMPLATE_TOKENS:
        flags = " <span class='flag bad'>nghi trả lời bằng template</span>"
    record_tools = [t for t in record["tool_calls"] if t != REGULATION_TOOL]
    regulation, reconstructed = _regulation_line(record, task, run, lookup)
    meta = (
        f"Lần hỏi {record['seed'] + 1} (seed {record['seed']}) · {record['latency_s']:.2f} s · {record['tokens']} token"
        f" · tool Student Record: {escape(', '.join(record_tools) or 'không gọi')}{flags}{regulation}"
    )
    if record["error"]:
        meta += f"<br><span class='flag bad'>lỗi: {escape(record['error'])}</span>"
    card = (
        f"<div class='answer'><div class='meta'>{meta}</div><ul class='check'>{items}</ul>"
        f"<div class='verdict {css}'>→ {label}{escape(tail)}</div>"
        f"<details><summary>Nguyên văn câu trả lời</summary><pre>{escape(record['text'])}</pre></details></div>"
    )
    return card, reconstructed


def _criteria_block(task: Task) -> str:
    expected = " hoặc ".join(OUTCOME_VI[o] for o in _expected_outcomes(task))
    who = f"tài khoản <code>{escape(task.user)}</code>" if task.user else "chưa đăng nhập"
    items = [f"Người hỏi: {who}", f"Kết cục cần có: <b>{expected}</b>"]
    if task.facts:
        facts = "; ".join(
            f"<code>{escape(f.field)}</code> = {escape(str(f.value))} "
            f"(chấp nhận: {', '.join(escape(m) for m in f.mention)})"
            for f in task.facts
        )
        items.append(f"Fact bắt buộc: {facts}")
    if task.forbidden:
        items.append("Mẫu cấm (regex): " + ", ".join(f"<code>{escape(p)}</code>" for p in task.forbidden))
    if task.reference_answer:
        items.append(f"Đáp án mẫu (cho người chấm): {escape(task.reference_answer)}")
    if task.notes:
        items.append(f"Ghi chú: {escape(task.notes)}")
    bullets = "".join(f"<li>{i}</li>" for i in items)
    return f"<div class='criteria'><b>Tiêu chí của câu này</b><ul>{bullets}</ul></div>"


def _task_table(runs: list[Run], tasks: dict[str, Task], lookup: RegulationLookup | None) -> tuple[str, bool]:
    by_run = [defaultdict(list) for _ in runs]
    for index, run in enumerate(runs):
        for record in run.records:
            by_run[index][record["task_id"]].append(record)
    order = [tid for tid in tasks if any(tid in b for b in by_run)]
    head = "".join(f"<th>{escape(r.name)}</th>" for r in runs)
    rows, reconstructed = [], False
    for tid in order:
        task = tasks[tid]
        cells, details = [], []
        for index, run in enumerate(runs):
            records = sorted(by_run[index].get(tid, []), key=lambda r: r["seed"])
            css, label = _verdict(records)
            if label[0].isdigit():
                label = f"{label} lần đạt"
            reasons = Counter(reason for r in records if r["passed"] is False for reason in fail_reasons(r, task))
            reason_text = "; ".join(f"{k} ×{v}" for k, v in reasons.items())
            reason_html = f"<span class='reason'>{escape(reason_text)}</span>" if reason_text else ""
            cells.append(f"<td><span class='badge {css}'>{label}</span>{reason_html}</td>")
            cards = []
            for record in records:
                card, rebuilt = _scorecard(record, task, run, lookup)
                cards.append(card)
                reconstructed |= rebuilt
            if cards:
                details.append(f"<h4>{escape(run.name)}</h4>{''.join(cards)}")
        rows.append(
            f"<tr><td><b>{escape(tid)}</b></td><td>{escape(GROUP_LABELS[task.group.value])}</td>"
            f"<td>{OUTCOME_VI[task.expected.value]}</td>{''.join(cells)}<td><details><summary>"
            f"{escape(task.question)}</summary>{_criteria_block(task)}{''.join(details)}</details></td></tr>"
        )
    table = (
        f"<table class='tasks'><thead><tr><th>Câu</th><th>Nhóm</th><th>Cần</th>{head}"
        "<th>Câu hỏi (bấm để xem tiêu chí và phiếu chấm từng lần hỏi)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return table, reconstructed


def _counts(records: list[dict]) -> dict[str, tuple[int, int]]:
    groups = defaultdict(list)
    for record in records:
        groups[record["group"]].append(record)
    graded = [r for r in records if r["passed"] is not None]
    answerable = groups[Group.BASIC.value] + groups[Group.PERSONAL.value]
    traps = groups[Group.OUT_OF_SCOPE.value]
    missing = groups[Group.MISSING_INFO.value]
    return {
        "pass_rate": (sum(r["passed"] is True for r in graded), len(graded)),
        "outcome_accuracy": (sum(r["outcome_ok"] for r in records), len(records)),
        "strict_refusal_rate": (sum(r["outcome"] == "refuse" for r in traps), len(traps)),
        "false_refusal_rate": (sum(r["outcome"] == "refuse" for r in answerable), len(answerable)),
        "clarification_rate": (sum(r["outcome"] == "clarify" for r in missing), len(missing)),
        "fact_recall": (sum(r["facts_hit"] for r in records), sum(r["facts_total"] for r in records)),
        "citation_recall": (sum(r["citations_hit"] for r in records), sum(r["citations_total"] for r in records)),
    }


def _metric_table(pairs: list[tuple[dict, list[dict]]], runs: list[Run]) -> str:
    head = "".join(f"<th class='num'>{escape(r.name)}</th>" for r in runs)
    tallies = [_counts(records) for _, records in pairs]
    body = []
    for key, label, direction in METRICS:
        values = [block.get(key) for block, _ in pairs]
        best = _best(values, direction)
        cells = []
        for index, value in enumerate(values):
            num, den = tallies[index].get(key, (None, 0))
            extra = f"<span class='count'>({num}/{den})</span>" if den else ""
            cells.append(f"<td class='num{' best' if index in best else ''}'>{_fmt(value)}{extra}</td>")
        hint = {"max": " ↑", "min": " ↓"}.get(direction or "", "")
        body.append(
            f"<tr><td>{escape(label)}<span class='hint'>{hint}</span>"
            f"<span class='reason'>{escape(METRIC_HELP.get(key, ''))}</span></td>{''.join(cells)}</tr>"
        )
    return f"<table><thead><tr><th>Chỉ số</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _tally_cards(runs: list[Run]) -> str:
    cards = []
    for index, run in enumerate(runs):
        records = run.records
        passed = sum(r["passed"] is True and not r["error"] for r in records)
        failed = sum(r["passed"] is False and not r["error"] for r in records)
        hand = sum(r["passed"] is None for r in records)
        errors = sum(bool(r["error"]) for r in records)
        color = PALETTE[index % len(PALETTE)]
        cards.append(
            f"<div class='card'><h4><span class='swatch' style='background:{color}'></span>{escape(run.name)}</h4>"
            f"<p>{len(records)} lượt = {run.summary.get('tasks', '?')} câu × {len(run.summary.get('seeds', []))} "
            "lần hỏi</p>"
            f"<div class='tally'><span class='t-pass'>{passed} đạt</span><span class='t-fail'>{failed} trượt</span>"
            f"<span class='t-hand'>{hand} chấm tay</span><span class='t-hand'>{errors} lỗi</span></div></div>"
        )
    return f"<div class='cards'>{''.join(cards)}</div>"


def _howto() -> str:
    groups = "".join(
        f"<div class='card'><h4>{escape(GROUP_LABELS[g])}</h4><p><b>Hệ thống phải:</b> {escape(must)}</p>"
        f"<p><b>Đạt khi:</b> {rule}</p></div>"
        for g, (must, rule) in GROUP_RULES.items()
    )
    return f"""<div class="howto">
<p>Mỗi câu hỏi được hỏi nhiều lần (mỗi seed một lần) để xem hệ thống có ổn định không; mỗi lần là một phiên mới.
Mỗi lần hỏi (một <b>lượt</b>) được máy chấm bằng luật cố định, không dùng LLM, qua 3 phép kiểm tra:</p>
<ol>
<li><b>Kết cục:</b> câu trả lời đang <i>trả lời</i>, <i>hỏi lại</i> hay <i>từ chối</i>? Nếu hệ thống không tự khai báo,
máy dò cụm từ: có cụm từ chối như {REFUSAL_EXAMPLES} → từ chối; có cụm hỏi lại như {CLARIFY_EXAMPLES}, hoặc câu cuối
kết thúc bằng “?” → hỏi lại; còn lại → trả lời. So với kết cục cần có của câu.</li>
<li><b>Fact:</b> câu trả lời có chứa đủ các số liệu bắt buộc không (so chuỗi, không phân biệt hoa thường).</li>
<li><b>Mẫu cấm:</b> câu trả lời có khớp regex nào trong danh sách cấm của câu không (lộ dữ liệu người khác, nói
ngược hồ sơ…).</li>
</ol>
<p><b>ĐẠT</b> = kết cục đúng <b>và</b> đủ fact <b>và</b> không khớp mẫu cấm. <b>TRƯỢT</b> = sai ít nhất một điều.
<b>CHẤM TAY</b> = kết cục đúng nhưng câu chưa có tiêu chí nội dung để máy kiểm tra (không tính vào Pass).
Ô “2/3 lần đạt” trong bảng từng câu nghĩa là đạt 2 trong 3 lần hỏi, không phải điểm.</p>
<p>Máy chấm dựa vào cụm từ và regex nên có thể nhận nhầm kết cục hoặc báo khớp mẫu cấm nhầm (ví dụ câu phủ định ở
xa). Phiếu chấm của từng lượt ghi rõ khớp cụm nào, ở đoạn nào, để người đọc kiểm tra lại.</p>
</div><div class="cards">{groups}</div>"""


RECONSTRUCTED_NOTE = """<p class="sub">Một số phiếu chấm ghi kết quả Regulation MCP <b>tra lại sau khi chạy</b>:
lần chạy đó chưa ghi lời gọi <code>search_regulations</code> vào danh sách tool. Bộ tìm kiếm quy chế theo từ khóa
là tất định, nên tra lại với đúng câu hỏi cho cùng kết quả nếu mã và dữ liệu Regulation MCP không đổi từ lúc chạy.
“Advisor có gọi” được suy ra khi câu trả lời là “Tôi chưa có nguồn quy chế…” (chỉ xuất hiện sau khi tra mà không
thấy) hoặc nhắc mã điều khoản tìm được.</p>"""


def render(
    runs: list[Run], title: str = "Kết quả đánh giá Advisor", regulation_lookup: RegulationLookup | None = None
) -> str:
    tasks = _all_tasks()
    table, reconstructed = _task_table(runs, tasks, regulation_lookup)
    groups = "".join(
        f"<h4>{escape(GROUP_LABELS[g])}</h4>"
        + _metric_table(
            [(r.summary["by_group"].get(g, {}), [x for x in r.records if x["group"] == g]) for r in runs], runs
        )
        for g in GROUP_LABELS
    )
    generated = time.strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{STYLE}{EXTRA_STYLE}</style></head>
<body><main>
<h1>{escape(title)}</h1>
<p class="sub">Tạo lúc {generated} bằng <code>co5151-eval report</code>. ↑ cao hơn là tốt, ↓ thấp hơn là tốt; ô tô xanh
là tốt nhất; số trong ngoặc là (đếm được / tổng).</p>
<h2>Tóm tắt</h2>{_tally_cards(runs)}
<h2>Cách chấm</h2>{_howto()}
<h2>Các cấu hình</h2>{_runs_section(runs)}
<h2>Cần kiểm tra</h2>{_warnings(runs)}
<h2>So sánh tổng</h2>{_metric_table([(r.summary["overall"], r.records) for r in runs], runs)}{_seed_line(runs)}
<h2>Pass theo nhóm câu hỏi</h2>{_bar_chart(runs)}
<h2>Từng câu</h2>
<p class="sub">Ô là số lần đạt / số lần hỏi, kèm lý do trượt. Bấm câu hỏi để xem tiêu chí và phiếu chấm từng lần
hỏi.</p>
{RECONSTRUCTED_NOTE if reconstructed else ""}{table}
<h2>Chi tiết theo nhóm</h2>{groups}
</main></body></html>
"""


def write_html_report(
    directories: list[Path],
    out: Path,
    title: str = "Kết quả đánh giá Advisor",
    regulation_lookup: RegulationLookup | None = None,
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render([load_run(d) for d in directories], title, regulation_lookup), "utf-8")
    return out
