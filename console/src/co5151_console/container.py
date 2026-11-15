"""Composition root: the only module that picks the adapters behind each port of the console."""

from dataclasses import dataclass

from .adapters.backend_http import HttpBackendAdmin
from .config import Settings
from .ports import BackendAdmin
from .services.traces import TraceBrowser


@dataclass
class Container:
    settings: Settings
    traces: TraceBrowser


def build_container(settings: Settings, *, admin: BackendAdmin | None = None) -> Container:
    """`admin`: for tests, instead of the backend's admin API over HTTP."""
    admin = admin or HttpBackendAdmin(settings.backend_url, settings.admin_token)
    return Container(settings=settings, traces=TraceBrowser(admin))
