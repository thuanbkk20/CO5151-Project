"""Composition root: the only module that picks the adapters behind each port."""

from dataclasses import dataclass

from .infrastructure.config import Settings


@dataclass
class Container:
    settings: Settings

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass


def build_container(settings: Settings) -> Container:
    return Container(settings=settings)
