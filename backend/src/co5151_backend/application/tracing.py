"""Records the spans of one answer: what each node (planner, MCP tools, writer, Verifier) received and returned.

The use case makes one `SpanRecorder` per answer and passes it down, like `emit`. Spans are saved with the trace and
read back through their own API route, never streamed: a draft the Verifier rejected is only visible afterwards.
"""

import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ..domain.trace import Span, Usage

MAX_TEXT = 2000
MAX_ITEMS = 20
MAX_DEPTH = 6
REDACTED = "[đã ẩn]"


def clip(value: Any, secrets: tuple[str, ...] = (), depth: int = 0) -> Any:
    """A JSON value of bounded size with every secret replaced: long strings and lists are cut, models become
    dicts. A rejected draft can hold what the Verifier caught (the canary), so it is redacted here too."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"… (+{len(value) - MAX_TEXT} ký tự)"
    if depth >= MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        return {str(k): clip(v, secrets, depth + 1) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        items = [clip(v, secrets, depth + 1) for v in list(value)[:MAX_ITEMS]]
        return items + [f"… (+{len(value) - MAX_ITEMS} mục)"] if len(value) > MAX_ITEMS else items
    return clip(str(value), secrets, depth)


@dataclass
class OpenSpan:
    """Filled in by the node while the span is open."""

    output: dict[str, Any] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    error: str | None = None


class SpanRecorder:
    def __init__(self, *, secrets: Iterable[str] = (), keep: bool = True):
        self._secrets = tuple(s for s in secrets if s)
        self._keep = keep
        self._start = time.perf_counter()
        self.spans: list[Span] = []

    @contextmanager
    def span(self, node: str, name: str, input: dict[str, Any]) -> Iterator[OpenSpan]:
        """`with spans.span(...) as s: s.output = ...`. An exception is recorded on the span and re-raised."""
        opened, start = OpenSpan(), time.perf_counter()
        try:
            yield opened
        except Exception as e:
            opened.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            if self._keep:
                self.spans.append(
                    Span(
                        node=node,
                        name=name,
                        input=clip(input, self._secrets),
                        output=clip(opened.output, self._secrets),
                        start_ms=_ms(self._start, start),
                        duration_ms=_ms(start, time.perf_counter()),
                        usage=opened.usage,
                        error=clip(opened.error, self._secrets),
                    )  # fmt: skip
                )


def _ms(a: float, b: float) -> int:
    return round((b - a) * 1000)


DISCARD = SpanRecorder(keep=False)
"""For callers that do not trace (tests, the eval's retrieval check)."""
