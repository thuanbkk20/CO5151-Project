"""Composition root: the only module that picks the adapters behind each port of the console."""

from dataclasses import dataclass

from .adapters.backend_http import HttpBackendAdmin
from .adapters.sqlite_store import SqliteStore
from .config import Settings
from .ports import BackendAdmin
from .services.question_sets import QuestionSets
from .services.traces import TraceBrowser


@dataclass
class Container:
    settings: Settings
    traces: TraceBrowser
    question_sets: QuestionSets


def build_container(settings: Settings, *, admin: BackendAdmin | None = None) -> Container:
    """`admin`: for tests, instead of the backend's admin API over HTTP."""
    admin = admin or HttpBackendAdmin(settings.backend_url, settings.admin_token)
    store = SqliteStore(settings.database)
    return Container(settings=settings, traces=TraceBrowser(admin), question_sets=QuestionSets(store))
