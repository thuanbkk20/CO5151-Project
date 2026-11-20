from dataclasses import replace

import pytest
from backend_fakes import Model, Models

from co5151_backend.application.agents.advisor.planner import LLMActionRouter
from co5151_backend.container import router_factory, verifier_factory
from co5151_backend.infrastructure.config import Settings
from co5151_backend.infrastructure.laya import LayaActionRouter

SETTINGS = Settings(token_secret=b"t", student_token_secret=b"s", database_url=None)


def test_verifier_modes():
    model = Model()
    llm = verifier_factory(SETTINGS, Models(model))
    assert llm(model).describe() == {"rule_checks": 2, "judge": {"provider": "fake", "model": "fake-1"}}
    assert llm(None).describe()["judge"] is None  # no LLM key: rule checks only
    assert verifier_factory(replace(SETTINGS, verifier_mode="rules"), Models(model))(model).describe()["judge"] is None
    assert verifier_factory(replace(SETTINGS, verifier_mode="off"), Models(model))(model) is None
    with pytest.raises(ValueError):
        verifier_factory(replace(SETTINGS, verifier_mode="typo"), Models(model))


def test_verifier_can_use_its_own_model_of_the_same_provider():
    asked = []

    class Picky(Models):
        def create(self, provider, model):
            asked.append((provider, model))
            return Model()

    verifier_factory(replace(SETTINGS, verifier_model="cheap"), Picky(Model()))(Model())
    assert asked == [("fake", "cheap")]


def test_planner_modes():
    model = Model()
    assert isinstance(router_factory(SETTINGS)(model), LLMActionRouter)
    assert router_factory(SETTINGS)(None) is None
    assert router_factory(replace(SETTINGS, planner_mode="rule"))(model) is None
    assert isinstance(router_factory(replace(SETTINGS, planner_mode="laya"))(None), LayaActionRouter)
    with pytest.raises(ValueError):
        router_factory(replace(SETTINGS, planner_mode="typo"))
