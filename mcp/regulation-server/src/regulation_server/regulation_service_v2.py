"""Integration service using the existing team error envelope; no registry edits."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
)

from co5151_contracts.envelope import ErrorCode, err, ok

from .handoff_retriever import HandoffRetriever


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
    hops: StrictInt = Field(default=2, ge=0, le=3)
    context: Context | None = None


class ProvisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provision_id: StrictStr = Field(min_length=1, max_length=200)
    hops: StrictInt = Field(default=2, ge=0, le=3)
    context: Context | None = None


INPUTS = {"search_regulations": SearchInput, "get_provision": ProvisionInput}


class RegulationServiceV2:
    def __init__(self, base, allow_draft=False):
        self.engine = HandoffRetriever(base)
        self.allow_draft = allow_draft

    def call(self, name, arguments):
        if name not in INPUTS:
            return err(ErrorCode.NOT_FOUND, "Không tìm thấy công cụ.")
        try:
            p = INPUTS[name].model_validate(arguments)
            if not (p.query if name == "search_regulations" else p.provision_id).strip():
                raise ValueError("empty input")
        except (ValidationError, ValueError):
            return err(ErrorCode.INVALID_ARGUMENT, "Tham số không hợp lệ.")
        if not self.allow_draft:
            return err(
                ErrorCode.FORBIDDEN,
                "Dữ liệu chưa được phê duyệt; cần bật chế độ bản nháp ở cấu hình server.",
            )
        context = p.context.model_dump(exclude_none=True) if p.context else {}
        try:
            result = (
                self.engine.search(p.query, p.top_k, p.hops, context)
                if name == "search_regulations"
                else self.engine.get(p.provision_id, p.hops, context)
            )
            return ok(result)
        except KeyError:
            return err(ErrorCode.NOT_FOUND, "Không tìm thấy điều khoản.")
        except Exception:  # noqa: BLE001 - redact errors at the tool boundary
            return err(ErrorCode.INTERNAL, "Không thể xử lý yêu cầu tra cứu.")
