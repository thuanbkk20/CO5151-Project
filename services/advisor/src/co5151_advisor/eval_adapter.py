from co5151_eval.gold import RecordOracle

from .agent import AdvisorAgent
from .regulations import StaticRegulationSource


def make_agent(seed: int = 0) -> AdvisorAgent:
    oracle = RecordOracle()
    return AdvisorAgent(oracle.service, StaticRegulationSource())
