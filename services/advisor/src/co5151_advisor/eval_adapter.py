import os
from functools import cache
from pathlib import Path
from typing import Any

import regulation_server
from co5151_eval.gold import RecordOracle
from regulation_server.regulation_service_v2 import RegulationServiceV2

from .agent import AdvisorAgent
from .llm import LLMClient
from .mcp_clients import McpRegulationService, McpStudentService
from .regulations import RegulationSource, StaticRegulationSource, ToolRegulationSource

REGULATION_BASE = Path(regulation_server.__file__).resolve().parents[2]
TRUE_VALUES = {"1", "true", "yes", "on"}


def _use_mcp(variable: str) -> bool:
    """`inprocess` (default) calls the service as a Python object; `mcp` goes through a real MCP client."""
    return os.environ.get(variable, "inprocess").strip().lower() == "mcp"


@cache
def _regulation_service(allow_draft: bool) -> RegulationServiceV2:
    return RegulationServiceV2(REGULATION_BASE, allow_draft=allow_draft)


@cache
def _regulation_mcp(allow_draft: bool) -> McpRegulationService:
    return McpRegulationService(allow_draft=allow_draft)


def student_service(local: Any) -> Any:
    """The Student Record tool service for the Advisor: `local` in-process, or the running `student-mcp serve`."""
    if not _use_mcp("ADVISOR_STUDENT_TRANSPORT"):
        return local
    default_url = (
        f"http://{os.environ.get('STUDENT_MCP_HOST', '127.0.0.1')}:{os.environ.get('STUDENT_MCP_PORT', '8102')}/mcp"
    )
    return McpStudentService(os.environ.get("STUDENT_MCP_URL") or default_url)


def regulation_source() -> RegulationSource:
    if os.environ.get("ADVISOR_REGULATION_SOURCE", "mcp").strip().lower() == "static":
        return StaticRegulationSource()
    allow_draft = os.environ.get("REGULATION_ALLOW_DRAFT", "true").strip().lower() in TRUE_VALUES
    if _use_mcp("ADVISOR_REGULATION_TRANSPORT"):
        return ToolRegulationSource(_regulation_mcp(allow_draft))
    return ToolRegulationSource(_regulation_service(allow_draft))


def regulation_ids(question: str) -> list[str]:
    return [doc.id for doc in regulation_source().search(question)]


def make_agent(seed: int = 0) -> AdvisorAgent:
    oracle = RecordOracle()
    return AdvisorAgent(oracle.service, regulation_source(), llm_client=LLMClient())
