"""HTTP routes. Each one checks the caller, calls one use case and maps the result to a response body."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..application.events import AnswerEvent
from ..container import Container
from ..domain.conversation import Feedback
from ..domain.errors import AnswerFailed, DomainError, Unauthenticated
from ..domain.principal import Principal
from . import schemas as s

logger = logging.getLogger(__name__)
router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def container(request: Request) -> Container:
    return request.app.state.container


Deps = Annotated[Container, Depends(container)]


def principal(c: Deps, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Principal:
    if credentials is None:
        raise Unauthenticated("missing bearer token")
    return c.authenticate.execute(credentials.credentials)


Caller = Annotated[Principal, Depends(principal)]


@router.post("/auth/login", tags=["auth"])
def login(body: s.LoginIn, c: Deps) -> s.SessionOut:
    return s.SessionOut.of(c.sign_in.execute(body.username, body.password))


@router.get("/me", tags=["auth"])
def me(caller: Caller) -> s.UserOut:
    return s.UserOut.of(caller)


@router.get("/llm/providers", tags=["chat"])
def llm_providers(c: Deps, _caller: Caller) -> s.LLMChoicesOut:
    providers, default = c.conversations.llm_choices()
    return s.LLMChoicesOut(providers=providers, default=default)


@router.get("/conversations", tags=["conversations"])
async def list_conversations(
    c: Deps,
    caller: Caller,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> s.ConversationPageOut:
    return s.ConversationPageOut.of(await c.conversations.list_page(caller, limit=limit, cursor=cursor, search=q))


@router.post("/conversations", status_code=status.HTTP_201_CREATED, tags=["conversations"])
async def start_conversation(body: s.ConversationIn, c: Deps, caller: Caller) -> s.ConversationOut:
    settings = body.settings.domain() if body.settings else None
    started = await c.conversations.start(caller, conversation_id=body.id, title=body.title, settings=settings)
    return s.ConversationOut.of(started)


@router.get("/conversations/{conversation_id}", tags=["conversations"])
async def get_conversation(conversation_id: str, c: Deps, caller: Caller) -> s.ConversationDetailOut:
    return s.ConversationDetailOut.of(await c.conversations.get(caller, conversation_id))


@router.patch("/conversations/{conversation_id}", tags=["conversations"])
async def update_conversation(
    conversation_id: str, body: s.ConversationPatch, c: Deps, caller: Caller
) -> s.ConversationOut:
    settings = body.settings.domain() if body.settings else None
    return s.ConversationOut.of(
        await c.conversations.update(caller, conversation_id, title=body.title, settings=settings)
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["conversations"])
async def delete_conversation(conversation_id: str, c: Deps, caller: Caller) -> Response:
    await c.conversations.delete(caller, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/messages", tags=["chat"])
async def ask(conversation_id: str, body: s.MessageIn, c: Deps, caller: Caller) -> s.AnswerOut:
    return s.AnswerOut.of(await c.ask.execute(caller, conversation_id, body.content))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    tags=["chat"],
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "`step`* then `answer` or `error`"}},
)
async def ask_stream(conversation_id: str, body: s.MessageIn, c: Deps, caller: Caller) -> StreamingResponse:
    """Server-sent events: `step` while the answer is prepared, then `answer` (same body as the sync route) once the
    Verifier has passed it, or `error`. A client that disconnects does not stop the answer: it is still saved."""
    await c.conversations.get(caller, conversation_id)  # 404 before the stream starts
    queue: asyncio.Queue[AnswerEvent | None] = asyncio.Queue()

    async def run() -> str:
        try:
            answer = await c.ask.execute(caller, conversation_id, body.content, emit=queue.put)
            return _sse("answer", s.AnswerOut.of(answer).model_dump(mode="json"))
        except AnswerFailed as e:
            return _sse("error", {"detail": "answer failed", "trace_id": e.trace_id})
        except DomainError as e:
            return _sse("error", {"detail": str(e)})
        except Exception:
            logger.exception("stream of conversation %s failed", conversation_id)
            return _sse("error", {"detail": "answer failed"})
        finally:
            await queue.put(None)

    async def stream() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        while (event := await queue.get()) is not None:
            yield _sse(event.type, event.data)
        yield await task

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.put("/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT, tags=["conversations"])
async def set_feedback(message_id: str, body: s.FeedbackIn, c: Deps, caller: Caller) -> Response:
    await c.conversations.set_feedback(caller, message_id, Feedback(body.value, body.comment))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT, tags=["conversations"])
async def delete_feedback(message_id: str, c: Deps, caller: Caller) -> Response:
    await c.conversations.set_feedback(caller, message_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/traces/{trace_id}", tags=["chat"])
async def get_trace(trace_id: str, c: Deps, caller: Caller) -> s.TraceOut:
    return s.TraceOut.of(await c.conversations.trace(caller, trace_id))
