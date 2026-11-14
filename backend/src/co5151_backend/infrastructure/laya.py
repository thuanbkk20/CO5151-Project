"""Laya (https://github.com/NandhaKishorM/laya) as the Advisor's next-step router.

Laya is a non-autoregressive decision engine: it maps the question and the evidence state to one of the typed
choices in a single forward pass (~20-40 ms), so routing costs no LLM call. Unreachable or unsure: no decision.
"""

import logging

import httpx

from ..application.ports import Routed
from ..domain.evidence import Action

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8000/v1/systemone"
CRITERIA = {
    Action.SUMMARY: "query academic summary, credits earned, gpa",
    Action.WARNINGS: "academic warnings, probation",
    Action.REGULATIONS: "search training regulations",
    Action.CLARIFY: "vague questions needing clarification",
    Action.REFUSE: "asking about other students or disallowed requests",
    Action.RESPOND: "synthesize final answer",
}


class LayaActionRouter:
    name = "laya"

    def __init__(self, url: str | None = None, timeout: float = 1.0):
        self.url = url or DEFAULT_URL
        self._timeout = timeout

    async def route(self, question: str, state: dict[str, bool], choices: list[Action]) -> Routed:
        payload = {
            "state": {"body": question, **state},
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": "Determine the next action for student academic advising",
                    "criteria": {a.value: CRITERIA[a] for a in choices},
                }
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
                choice = response.json().get("answers", {}).get("action", {}).get("choice")
        except (httpx.HTTPError, ValueError, AttributeError) as e:
            logger.debug("Laya decision call failed: %s", e)
            return Routed(None, error=f"laya: {type(e).__name__}")
        action = next((a for a in choices if a.value == choice), None)
        return Routed(action, error=None if action else f"laya: unexpected choice {choice!r}")
