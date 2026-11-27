import json

from co5151_contracts.envelope import ErrorCode, err, ok
from co5151_eval import cli, retrieval
from co5151_eval.retrieval import RetrievalCase


def _case(*expected):
    return RetrievalCase(id="H01-1", query="q", expected=list(expected))


def _result(id_, superseded=()):
    return {"id": id_, "superseded": list(superseded), "evidence": {"source_text": "x" * 2000}}


def test_cases_load_and_have_unique_ids():
    cases = retrieval.load_cases()
    assert len(cases) >= 30
    assert len({c.id for c in cases}) == len(cases)


def test_rank_of_first_expected_gives_reciprocal_rank():
    row = retrieval.score_case(_case("B", "C"), ok({"results": [_result("A"), _result("B"), _result("X")]}))
    assert row["rr"] == 0.5
    assert row["recall@3"] == 0.5 and row["hit@3"]
    assert row["chars"] == 3 * retrieval.MAX_CHARS


def test_a_newer_version_stands_for_the_one_it_replaces():
    row = retrieval.score_case(_case("OLD"), ok({"results": [_result("NEW", superseded=["OLD"])]}))
    assert row["rr"] == 1.0 and row["recall@3"] == 1.0


def test_an_error_counts_as_empty():
    row = retrieval.score_case(_case("A"), err(ErrorCode.FORBIDDEN, "no"))
    assert row["n"] == 0 and row["rr"] == 0.0 and not row["hit@8"]
    assert retrieval.summarize([row])["empty_rate"] == 1.0


def test_cli_measures_the_bm25_engine(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert cli.main(["retrieval", "--engine", "bm25", "--json", str(out)]) == 0
    assert "Truy xuất quy chế: bm25" in capsys.readouterr().out
    data = json.loads(out.read_text("utf-8"))
    assert data["summary"]["cases"] == len(retrieval.load_cases())
