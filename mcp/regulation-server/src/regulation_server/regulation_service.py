"""Regulation service adapter using the team's existing result envelope.

This is a service layer, not an MCP transport server. Tool names are local
proposals until the shared registry is integrated by the group.
"""

import argparse
import json
from pathlib import Path

from co5151_contracts.envelope import ErrorCode, err, ok
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError
from retrieve_regulations import RegulationRetriever


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: StrictStr = Field(min_length=1, max_length=2000)
    top_k: StrictInt = Field(default=3, ge=1, le=5)
    hops: StrictInt = Field(default=1, ge=0, le=2)


class ProvisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provision_id: StrictStr = Field(min_length=1, max_length=160)


INPUTS = {"search_regulations": SearchInput, "get_provision": ProvisionInput}


class RegulationService:
    def __init__(self, graph_path, allow_draft=False):
        self.engine = RegulationRetriever(graph_path)
        # Server-side setting. The caller cannot opt into draft access in tool args.
        self.allow_draft = allow_draft

    def describe(self):
        return {
            "registry_status": "local_proposal_not_shared_registry",
            "tools": [
                {
                    "name": name,
                    "permission": "read-only",
                    "input_schema": model.model_json_schema(),
                }
                for name, model in INPUTS.items()
            ],
            "response_envelope": "{ok:true,data:...} | {ok:false,error:{code,message}}",
            "transport": "not_implemented",
            "draft_enabled": self.allow_draft,
        }

    def call(self, name, args):
        if name not in INPUTS:
            return err(ErrorCode.NOT_FOUND, "Không tìm thấy công cụ.")
        try:
            parsed = INPUTS[name].model_validate(args)
            if name == "search_regulations" and not parsed.query.strip():
                raise ValueError("empty query")
        except (ValidationError, ValueError):
            return err(ErrorCode.INVALID_ARGUMENT, "Tham số không hợp lệ.")
        if not self.allow_draft:
            return err(
                ErrorCode.FORBIDDEN,
                "Dữ liệu chưa được phê duyệt; chế độ xem bản nháp chưa bật.",
            )
        try:
            if name == "search_regulations":
                return ok(
                    self.engine.search(
                        parsed.query, parsed.top_k, parsed.hops, allow_draft=True
                    )
                )
            node = self.engine.nodes.get(parsed.provision_id)
            if node is None or node["type"] != "Provision":
                return err(ErrorCode.NOT_FOUND, "Không tìm thấy điều khoản.")
            d = node["data"]
            return ok(
                {
                    "status": "draft_evidence",
                    "corpus_version": self.engine.version,
                    "provision_id": node["id"],
                    "verified": False,
                    "evidence": d,
                    "citation": {
                        "source_id": d["source_id"],
                        "unit_id": d["unit_id"],
                        "pdf_page": d["pdf_page"],
                    },
                    "eligibility_decision": None,
                    "warnings": [
                        "Unapproved evidence; program/cohort/date scope has not been resolved."
                    ],
                }
            )
        except Exception:  # noqa: BLE001 - redact errors at the tool boundary
            # Do not expose paths, raw inputs or tracebacks across the tool boundary.
            return err(ErrorCode.INTERNAL, "Không thể xử lý yêu cầu tra cứu.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--allow-draft", action="store_true")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--query")
    group.add_argument("--provision-id")
    group.add_argument("--describe", action="store_true")
    a = p.parse_args()
    service = RegulationService(
        a.base / "data/processed/language_structured/evidence_graph.json", a.allow_draft
    )
    if a.describe:
        result = service.describe()
    elif a.query is not None:
        result = service.call(
            "search_regulations", {"query": a.query, "top_k": 1}
        ).model_dump(mode="json", exclude_none=True)
    else:
        result = service.call(
            "get_provision", {"provision_id": a.provision_id}
        ).model_dump(mode="json", exclude_none=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
