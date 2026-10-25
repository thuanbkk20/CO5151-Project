import os
from functools import cache
from pathlib import Path

import regulation_server
from co5151_eval.gold import RecordOracle
from regulation_server.regulation_service_v2 import RegulationServiceV2

from .agent import AdvisorAgent
from .llm import LLMClient
from .regulations import RegulationSource, StaticRegulationSource, ToolRegulationSource

REGULATION_BASE = Path(regulation_server.__file__).resolve().parents[2]
TRUE_VALUES = {"1", "true", "yes", "on"}


@cache
def _regulation_service(allow_draft: bool) -> RegulationServiceV2:
    return RegulationServiceV2(REGULATION_BASE, allow_draft=allow_draft)


def regulation_source() -> RegulationSource:
    if os.environ.get("ADVISOR_REGULATION_SOURCE", "mcp").strip().lower() == "static":
        return StaticRegulationSource()
    allow_draft = os.environ.get("REGULATION_ALLOW_DRAFT", "true").strip().lower() in TRUE_VALUES
    return ToolRegulationSource(_regulation_service(allow_draft))


def regulation_ids(question: str) -> list[str]:
    return [doc.id for doc in regulation_source().search(question)]


def make_agent(seed: int = 0) -> AdvisorAgent:
    oracle = RecordOracle()
    return AdvisorAgent(oracle.service, regulation_source(), llm_client=LLMClient())
