from co5151_advisor.eval_adapter import regulation_ids, regulation_source
from co5151_advisor.regulations import StaticRegulationSource, ToolRegulationSource
from co5151_contracts import ErrorCode, err, ok


class _Forbidden:
    def call(self, name, arguments):
        return err(ErrorCode.FORBIDDEN, "draft")


class _Results:
    def __init__(self, *evidence):
        self._results = [{"id": e["provision_id"], "evidence": e} for e in evidence]

    def call(self, name, arguments):
        return ok({"results": self._results})


def test_text_is_read_from_whichever_field_the_evidence_carries():
    source = ToolRegulationSource(
        _Results(
            {"provision_id": "QD-CL5.5", "fragments": [{"text": "5.5 Đăng ký"}, {"text": "học phần"}]},
            {"provision_id": "A2-THESIS", "fragments": None, "source_text": "Khi xét\n\nđiều kiện"},
            {"provision_id": "FAQ-6", "text": "Hỏi đáp tốt nghiệp", "source_text": "bản gốc"},
        )
    )
    assert [d.content for d in source.search("luận văn")] == [
        "5.5 Đăng ký học phần",
        "Khi xét điều kiện",
        "Hỏi đáp tốt nghiệp",
    ]


def test_every_result_for_the_eval_questions_has_text(monkeypatch):
    from co5151_eval.tasks import load_tasks

    monkeypatch.delenv("ADVISOR_REGULATION_SOURCE", raising=False)
    monkeypatch.delenv("REGULATION_ALLOW_DRAFT", raising=False)
    source = regulation_source()
    docs = [d for task in load_tasks() for d in source.search(task.question)]
    assert docs and all(d.content for d in docs)


def test_adapter_reads_the_real_regulation_corpus(monkeypatch):
    monkeypatch.delenv("ADVISOR_REGULATION_SOURCE", raising=False)
    monkeypatch.delenv("REGULATION_ALLOW_DRAFT", raising=False)
    source = regulation_source()
    assert isinstance(source, ToolRegulationSource)
    docs = source.search("Điều kiện làm đồ án tốt nghiệp")
    assert docs and all(d.id and d.content for d in docs)
    assert all(len(d.content) <= 1500 for d in docs)


def test_static_source_can_still_be_selected(monkeypatch):
    monkeypatch.setenv("ADVISOR_REGULATION_SOURCE", "static")
    assert isinstance(regulation_source(), StaticRegulationSource)


def test_tool_error_yields_no_documents():
    assert ToolRegulationSource(_Forbidden()).search("tốt nghiệp") == []


def test_regulation_ids_lists_the_provisions_found(monkeypatch):
    monkeypatch.delenv("ADVISOR_REGULATION_SOURCE", raising=False)
    monkeypatch.delenv("REGULATION_ALLOW_DRAFT", raising=False)
    assert regulation_ids("Điều kiện làm đồ án tốt nghiệp")
    assert regulation_ids("Thời gian tối đa để hoàn thành chương trình đại học chính quy là bao lâu?") == []
