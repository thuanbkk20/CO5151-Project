"""rescore: a finished run graded again without calling the agent."""

import json

from co5151_eval.cli import main


def _run(tmp_path, *args):
    out = tmp_path / "run"
    assert main(["run", *args, "--out", str(out)]) == 0
    return out


def test_rescore_a_conversation_run_gives_the_same_scores(tmp_path):
    out = _run(tmp_path, "--agent", "co5151_eval.baselines:refuse_all", "--only", "H14,H15")
    assert main(["rescore", str(out / "results.jsonl")]) == 0
    before = json.loads((out / "summary.json").read_text("utf-8"))
    after = json.loads((out / "rescored" / "summary.json").read_text("utf-8"))
    assert after["by_conversation"] == before["by_conversation"] and after["turns"] == before["turns"]
    assert after["rescored_from"].endswith("results.jsonl") and after["agent"] == before["agent"]


def test_rescore_uses_the_current_scorer(tmp_path):
    out = _run(tmp_path, "--agent", "co5151_eval.baselines:refuse_all", "--only", "H14")
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text("utf-8").splitlines()]
    rows[0]["text"] = "Mình không thể xác nhận là bạn đủ điều kiện tốt nghiệp. Học phí 500.000 đồng."
    rows[0]["passed"], rows[0]["forbidden_hits"] = True, []  # what an old scorer said
    (out / "results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), "utf-8")
    assert main(["rescore", str(out / "results.jsonl"), "--out", str(tmp_path / "new")]) == 0
    first = json.loads((tmp_path / "new" / "results.jsonl").read_text("utf-8").splitlines()[0])
    assert first["forbidden_hits"] and first["passed"] is False and first["latency_s"] == rows[0]["latency_s"]


def test_rescore_a_single_question_run(tmp_path):
    out = _run(tmp_path, "--suite", "tasks", "--agent", "co5151_eval.baselines:refuse_all", "--only", "O01,P01")
    assert main(["rescore", str(out / "results.jsonl")]) == 0
    assert json.loads((out / "rescored" / "summary.json").read_text("utf-8"))["overall"]["n"] == 2
