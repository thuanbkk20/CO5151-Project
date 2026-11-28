import json

from regulation_graph.build import build
from regulation_graph.documents import DATA


def test_committed_graph_is_up_to_date():
    """Edit the data or the splitter, then run `regulation-graph-build` and commit graph.json."""
    committed = json.loads((DATA / "graph.json").read_text("utf-8"))
    assert committed["version"] == build()["version"]


def _graph():
    g = json.loads((DATA / "graph.json").read_text("utf-8"))
    return {p["id"]: p for p in g["provisions"]}, g["edges"]


def test_articles_clauses_and_appendices_are_split():
    provisions, edges = _graph()
    assert provisions["QD2931-2021-ART17"]["title"] == "Điều 17. Học lại, thi và học cải thiện điểm"
    assert "5,5 điểm thang 10,0" in provisions["QD2932-2021-CL7.5"]["text"]
    assert provisions["QD2932-2021-CL7.5"]["pages"] == [8, 9]
    assert {"source": "QD2931-2021-ART14", "relation": "CONTAINS", "target": "QD2931-2021-CL14.2"} in edges


def test_amendments_point_from_the_new_text_to_the_old_one():
    provisions, edges = _graph()
    assert provisions["QD1259-2026-CL14.2"]["text"].startswith("a) Loại đạt có phân mức")
    amends = {(e["source"], e["target"]) for e in edges if e["relation"] == "AMENDS"}
    assert ("QD1259-2026-CL14.2", "QD2931-2021-CL14.2") in amends
    assert ("QD1260-2026-CL5.5", "QD2933-2021-CL5.5") in amends
    replaces = {(e["source"], e["target"]) for e in edges if e["relation"] == "REPLACES"}
    assert ("QD2749-2026-APP1", "QD1260-2026-APP1") in replaces


def test_letterhead_lines_are_not_part_of_the_text():
    provisions, _ = _graph()
    assert "Lý Thường Kiệt" not in provisions["QD2931-2021-ART24"]["text"]


def test_concepts_link_words_to_provisions():
    g = json.loads((DATA / "graph.json").read_text("utf-8"))
    concepts = {c["id"]: c for c in g["concepts"]}
    assert "nhận bằng" in concepts["tot_nghiep"]["synonyms"]
    about = {(e["source"], e["target"]) for e in g["edges"] if e["relation"] == "ABOUT"}
    assert ("QD2749-2026-APP1", "chuan_ngoai_ngu") in about
    requires = {(e["source"], e["target"]) for e in g["edges"] if e["relation"] == "REQUIRES"}
    assert ("tot_nghiep", "chuan_ngoai_ngu") in requires
