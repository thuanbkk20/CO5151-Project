import json

import pytest

from co5151_eval import security
from co5151_eval.cli import main
from co5151_eval.gold import RecordOracle


@pytest.fixture(scope="module")
def results():
    return {r.id: r for r in security.run_suite()}


def test_at_least_ten_attack_cases():
    assert len(security.CASES) >= 10 and len({c.id for c in security.CASES}) == len(security.CASES)


def test_every_case_passes_on_current_server(results):
    failed = {i: r.observed for i, r in results.items() if not r.passed}
    assert failed == {}


def test_tampered_token_keeps_signature():
    oracle = RecordOracle()
    tok = oracle.token("sv001")
    forged = security.tamper(tok, student_id="2310002")
    assert forged.split(".")[1] == tok.split(".")[1] and forged != tok


def test_a_crashing_case_is_reported_not_raised():
    def boom(probe):
        raise RuntimeError("x")

    [r] = security.run_cases("http://127.0.0.1:9/mcp", RecordOracle(), [security.Case("X", "-", "-", "-", boom)])
    assert not r.passed and "RuntimeError" in r.observed


def test_cli_writes_markdown_and_json(tmp_path, capsys):
    out = tmp_path / "sec.json"
    assert main(["security", "--json", str(out)]) == 0
    assert "16/16 ca đạt" in capsys.readouterr().out
    assert len(json.loads(out.read_text())) == 16
