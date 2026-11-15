"""Composition root: the only module that picks the adapters behind each port of the console."""

from dataclasses import dataclass

from .adapters.backend_agent import HttpAnswerAgent
from .adapters.backend_http import HttpBackendAdmin
from .adapters.sqlite_store import SqliteStore
from .config import Settings
from .ports import AnswerAgent, BackendAdmin
from .services.evaluation import Evaluation
from .services.question_sets import QuestionSets
from .services.sessions import SessionBrowser
from .services.traces import TraceBrowser


@dataclass
class Container:
    settings: Settings
    traces: TraceBrowser
    sessions: SessionBrowser
    question_sets: QuestionSets
    evaluation: Evaluation


def build_container(
    settings: Settings, *, admin: BackendAdmin | None = None, agent: AnswerAgent | None = None, background=None
) -> Container:
    """`admin`, `agent`, `background`: for tests, instead of the backend over HTTP and a thread per run."""
    admin = admin or HttpBackendAdmin(settings.backend_url, settings.admin_token)
    agent = agent or HttpAnswerAgent(settings.backend_url, settings.eval_password)
    store = SqliteStore(settings.database)
    store.interrupt_running()  # a run cannot survive a restart of the console
    evaluation = Evaluation(store, store, agent, **({"background": background} if background else {}))
    return Container(settings=settings, traces=TraceBrowser(admin), sessions=SessionBrowser(admin),
                     question_sets=QuestionSets(store), evaluation=evaluation)  # fmt: skip
