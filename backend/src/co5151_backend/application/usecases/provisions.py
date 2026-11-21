"""Read one provision of the regulations by the id a citation gives (`Trace.citations`), so a reader can check what
an answer is based on. Regulations are public: any signed-in caller, guests included, may read them."""

import logging
from typing import Any

from co5151_contracts import ErrorCode

from ...domain.errors import InvalidRequest, NotFound, Unavailable
from ...domain.evidence import Provision
from ..ports import RegulationGateway

logger = logging.getLogger(__name__)
PROVISION_TOOL = "get_provision"
MAX_ID = 160  # the Regulation MCP's own limit on provision_id


class ReadProvision:
    def __init__(self, regulations: RegulationGateway):
        self._regulations = regulations

    async def execute(self, provision_id: str) -> Provision:
        provision_id = provision_id.strip()
        if not 0 < len(provision_id) <= MAX_ID:
            raise InvalidRequest(f"provision id must be 1 to {MAX_ID} characters")
        res = await self._regulations.call(PROVISION_TOOL, {"provision_id": provision_id})
        if not res.ok:
            if res.error.code in (ErrorCode.NOT_FOUND, ErrorCode.INVALID_ARGUMENT):
                raise NotFound(provision_id)
            logger.warning("get_provision %s failed: %s", provision_id, res.error.code)
            raise Unavailable("regulation service unavailable")
        try:
            return provision_of(res.data)
        except (KeyError, IndexError, TypeError, ValueError):
            logger.exception("get_provision %s returned an unexpected shape", provision_id)
            raise Unavailable("regulation service unavailable") from None


def provision_of(data: dict[str, Any]) -> Provision:
    """The first result of `get_provision` (Regulation MCP v2: `{results: [{id, citation, evidence}]}`)."""
    result = data["results"][0]
    evidence, citation = result["evidence"], result.get("citation") or {}
    # Decisions carry `fragments` (one per PDF page); language rules only `source_text`; handbook units `text`.
    fragments = [f.get("text", "").strip() for f in evidence.get("fragments") or []]
    text = "\n".join(f for f in fragments if f) or evidence.get("text") or evidence.get("source_text") or ""
    return Provision(
        id=evidence.get("provision_id") or result["id"],
        title=evidence.get("title") or result["id"],
        source=citation.get("file_name") or evidence.get("file_name") or "",
        pages=citation.get("pdf_pages") or evidence.get("pdf_pages") or [],
        text=text.strip(),
        verified=bool(result.get("verified", evidence.get("verified", False))),
        note=evidence.get("warning"),
    )
