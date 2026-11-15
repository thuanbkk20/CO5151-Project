"""Composition root: the only module that picks the adapters behind each port of the console."""

from dataclasses import dataclass

from .config import Settings


@dataclass
class Container:
    settings: Settings


def build_container(settings: Settings) -> Container:
    return Container(settings=settings)
