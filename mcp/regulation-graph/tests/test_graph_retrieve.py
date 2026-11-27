import pytest

from regulation_graph.retrieve import GraphRetriever
from regulation_graph.service import RegulationGraphService


@pytest.fixture(scope="module")
def r():
    return GraphRetriever()


def _ids(result):
    return [x["id"] for x in result["results"]]


def test_ocr_glued_syllables_are_split(r):
    assert r.syllables.split("kỳchính") == ("kỳ", "chính")
    assert r.syllables.split("tín") == ("tín",)


def test_the_version_in_force_replaces_the_old_one(r):
    res = r.search("Điều kiện đăng ký học phần Đồ án chuyên ngành")
    by_id = {x["id"]: x for x in res["results"]}
    assert "QD1260-2026-CL5.5" in by_id
    assert "QD2933-2021-CL5.5" in by_id["QD1260-2026-CL5.5"]["superseded"]
    assert "QD2933-2021-CL5.5" not in by_id


def test_a_replaced_appendix_resolves_to_the_latest_one(r):
    assert r.current("QD2933-2021-APP1")[0] == ["QD2749-2026-APP1"]
    assert r.current("QD2933-2021-ART4")[0] == []  # repealed by QĐ 1260


def test_synonyms_find_the_rule_without_its_words(r):
    assert "QD1260-2026-CL10.1" in _ids(r.search("Điều kiện để nhận bằng ấy ạ"))
    assert "QD2931-2021-ART17" in _ids(r.search("Học cải thiện thì lấy điểm nào?"))


def test_a_longer_phrase_wins_over_the_words_inside_it(r):
    assert r.matched_concepts("Em muốn làm luận văn tốt nghiệp")[0] == "hoc_phan_tot_nghiep"
    assert "tot_nghiep" not in r.matched_concepts("Em muốn làm luận văn tốt nghiệp")


def test_graduation_pulls_in_the_language_standard(r):
    res = r.search("Điều kiện xét tốt nghiệp gồm những gì?")
    assert "QD2749-2026-APP1" in _ids(res)
    assert any(x["reason"].startswith("requires:tot_nghiep") for x in res["results"])


def test_nothing_is_returned_out_of_scope(r):
    assert r.search("Hôm nay trời mưa không?")["status"] == "no_evidence"


def test_service_keeps_the_tools_and_envelope():
    svc = RegulationGraphService()
    res = svc.call("search_regulations", {"query": "thang điểm chữ", "top_k": 3, "hops": 1})
    assert res.ok and res.data["results"][0]["evidence"]["source_text"]
    assert svc.call("get_provision", {"provision_id": "QD2933-2021-CL5.5"}).data["results"][1]["id"] == (
        "QD1260-2026-CL5.5"
    )
    assert svc.call("get_provision", {"provision_id": "nope"}).error.code.value == "NOT_FOUND"
    assert svc.call("search_regulations", {"query": ""}).error.code.value == "INVALID_ARGUMENT"
    assert svc.call("drop_tables", {}).error.code.value == "NOT_FOUND"
