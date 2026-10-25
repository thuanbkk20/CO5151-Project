from co5151_advisor.eval_adapter import regulation_source
from co5151_advisor.regulations import StaticRegulationSource, ToolRegulationSource
from co5151_contracts import ErrorCode, err


class _Forbidden:
    def call(self, name, arguments):
        return err(ErrorCode.FORBIDDEN, "draft")


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
