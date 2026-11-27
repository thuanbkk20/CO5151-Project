"""The two regulation tools over the graph, with the same names, inputs and envelope as the BM25 Regulation MCP."""

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, field_validator

from co5151_contracts.envelope import ErrorCode, ToolResult, err, ok

from .retrieve import GraphRetriever


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    program: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    cohort: StrictInt | None = Field(default=None, ge=1990, le=2100)
    semester: StrictStr | None = Field(default=None, min_length=1, max_length=60)
    as_of_date: StrictStr | None = None

    @field_validator("as_of_date")
    @classmethod
    def iso_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Expected YYYY-MM-DD")
        return value


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: StrictStr = Field(min_length=1, max_length=2000)
    top_k: StrictInt = Field(default=3, ge=1, le=5)
    hops: StrictInt = Field(default=1, ge=0, le=3)
    context: Context | None = None


class ProvisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provision_id: StrictStr = Field(min_length=1, max_length=200)
    hops: StrictInt = Field(default=1, ge=0, le=3)
    context: Context | None = None


INPUTS = {"search_regulations": SearchInput, "get_provision": ProvisionInput}


class RegulationGraphService:
    def __init__(self, graph_path: Path | None = None):
        self.engine = GraphRetriever(graph_path)

    def call(self, name: str, arguments: dict) -> ToolResult:
        if name not in INPUTS:
            return err(ErrorCode.NOT_FOUND, "Không tìm thấy công cụ.")
        try:
            p = INPUTS[name].model_validate(arguments)
            if not (p.query if name == "search_regulations" else p.provision_id).strip():
                raise ValueError("empty input")
        except (ValidationError, ValueError):
            return err(ErrorCode.INVALID_ARGUMENT, "Tham số không hợp lệ.")
        context = p.context.model_dump(exclude_none=True) if p.context else {}
        try:
            if name == "search_regulations":
                return ok(self.engine.search(p.query, p.top_k, p.hops, context))
            return ok(self.engine.get(p.provision_id, p.hops, context))
        except KeyError:
            return err(ErrorCode.NOT_FOUND, "Không tìm thấy điều khoản.")
