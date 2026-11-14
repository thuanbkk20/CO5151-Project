"""Chat history on SQLAlchemy (SQLite or PostgreSQL): implements ConversationRepository and TraceRepository.

Rules kept from the earlier chat store, each fixing a failure seen in practice:
- every query is filtered by owner, so one user can never read or change another user's conversation;
- a row is created with a single `INSERT ... ON CONFLICT`, never "read, then insert if missing", so two concurrent
  creates of the same conversation both succeed.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, delete, event, or_, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ...domain.conversation import (
    MAX_TITLE,
    ChatSettings,
    Conversation,
    ConversationPage,
    Feedback,
    Message,
    MessageRole,
    utcnow,
)
from ...domain.errors import NotFound
from ...domain.trace import Outcome, Trace, Usage
from .tables import Base, ConversationRow, MessageRow, TraceRow

SUPPORTED_BACKENDS = ("sqlite", "postgresql")
_INSERT = {"sqlite": sqlite.insert, "postgresql": postgresql.insert}


class UnsupportedDatabase(ValueError):
    pass


def _utc(value: datetime | None) -> datetime | None:
    """SQLite gives back naive datetimes; every value is stored in UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def create_engine(url: str) -> AsyncEngine:
    """An async engine for `url`. A SQLite file gets its folder created, WAL and foreign keys."""
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend not in SUPPORTED_BACKENDS:
        raise UnsupportedDatabase(f"CHAT_DATABASE_URL must be SQLite or PostgreSQL, got {backend!r}")
    if backend == "postgresql":
        return create_async_engine(url, pool_pre_ping=True)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url, connect_args={"timeout": 30})

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # readers do not block the writer
        cursor.close()

    return engine


class SqlChatRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self._insert = _INSERT[engine.dialect.name]
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str) -> "SqlChatRepository":
        return cls(create_engine(url))

    async def create_schema(self) -> None:
        """Create the missing tables; existing tables and rows are left untouched."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session, session.begin():
            yield session

    @staticmethod
    def _owned(conversation_id: str, owner_id: str):
        return and_(ConversationRow.id == conversation_id, ConversationRow.owner_id == owner_id)

    # Conversations -----------------------------------------------------------------------------------------

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._session() as s:
            await s.execute(
                self._insert(ConversationRow.__table__)
                .values(
                    id=conversation.id,
                    owner_id=conversation.owner_id,
                    title=_title(conversation.title),
                    settings=asdict(conversation.settings),
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            row = await s.get(ConversationRow, conversation.id)
            if row.owner_id != conversation.owner_id:
                raise NotFound(conversation.id)
            return _conversation(row)

    async def get(self, conversation_id: str, owner_id: str) -> Conversation | None:
        async with self._session() as s:
            row = await s.scalar(select(ConversationRow).where(self._owned(conversation_id, owner_id)))
            if row is None:
                return None
            messages = await s.scalars(
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.created_at, MessageRow.id)
            )
            return _conversation(row, [_message(m) for m in messages])

    async def list_by_owner(
        self, owner_id: str, *, limit: int = 20, cursor: str | None = None, search: str | None = None
    ) -> ConversationPage:
        async with self._session() as s:
            query = select(ConversationRow).where(ConversationRow.owner_id == owner_id)
            if search:
                query = query.where(ConversationRow.title.icontains(search))
            if cursor:
                last = await s.scalar(select(ConversationRow).where(self._owned(cursor, owner_id)))
                if last is not None:
                    query = query.where(
                        or_(
                            ConversationRow.updated_at < last.updated_at,
                            and_(ConversationRow.updated_at == last.updated_at, ConversationRow.id < last.id),
                        )
                    )
            query = query.order_by(ConversationRow.updated_at.desc(), ConversationRow.id.desc()).limit(limit + 1)
            rows = (await s.scalars(query)).all()
            items = [_conversation(r) for r in rows[:limit]]
            return ConversationPage(items, next_cursor=items[-1].id if len(rows) > limit else None)

    async def update(
        self, conversation_id: str, owner_id: str, *, title: str | None = None, settings: ChatSettings | None = None
    ) -> Conversation | None:
        values: dict = {}
        if title is not None:
            values["title"] = _title(title)
        if settings is not None:
            values["settings"] = asdict(settings)
        async with self._session() as s:
            if values:
                await s.execute(update(ConversationRow).where(self._owned(conversation_id, owner_id)).values(**values))
            row = await s.scalar(select(ConversationRow).where(self._owned(conversation_id, owner_id)))
            return _conversation(row) if row else None

    async def delete(self, conversation_id: str, owner_id: str) -> bool:
        async with self._session() as s:
            if await s.scalar(select(ConversationRow.id).where(self._owned(conversation_id, owner_id))) is None:
                return False
            for table in (TraceRow, MessageRow):
                await s.execute(delete(table).where(table.conversation_id == conversation_id))
            await s.execute(delete(ConversationRow).where(ConversationRow.id == conversation_id))
            return True

    # Messages ----------------------------------------------------------------------------------------------

    async def add_message(self, message: Message) -> None:
        async with self._session() as s:
            s.add(
                MessageRow(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    role=message.role.value,
                    content=message.content,
                    trace_id=message.trace_id,
                    created_at=message.created_at,
                )
            )
            await s.execute(
                update(ConversationRow)
                .where(ConversationRow.id == message.conversation_id)
                .values(updated_at=max(message.created_at, utcnow()))
            )

    async def recent_messages(self, conversation_id: str, limit: int) -> list[Message]:
        async with self._session() as s:
            rows = await s.scalars(
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
                .limit(limit)
            )
            return [_message(r) for r in reversed(rows.all())]

    async def set_feedback(self, message_id: str, owner_id: str, feedback: Feedback | None) -> bool:
        owned = select(ConversationRow.id).where(ConversationRow.owner_id == owner_id)
        async with self._session() as s:
            result = await s.execute(
                update(MessageRow)
                .where(
                    MessageRow.id == message_id,
                    MessageRow.role == MessageRole.ASSISTANT.value,
                    MessageRow.conversation_id.in_(owned),
                )
                .values(
                    feedback_value=feedback.value if feedback else None,
                    feedback_comment=feedback.comment if feedback else None,
                )
            )
            return bool(result.rowcount)

    # Traces ------------------------------------------------------------------------------------------------

    async def save(self, trace: Trace) -> None:
        values = {
            "trace_id": trace.trace_id,
            "conversation_id": trace.conversation_id,
            "user_message_id": trace.user_message_id,
            "answer_message_id": trace.answer_message_id,
            "outcome": trace.outcome.value if trace.outcome else None,
            "steps": trace.steps,
            "tool_calls": trace.tool_calls,
            "citations": trace.citations,
            "verifier_rounds": trace.verifier_rounds,
            "input_tokens": trace.usage.input_tokens,
            "output_tokens": trace.usage.output_tokens,
            "latency_ms": trace.latency_ms,
            "llm": trace.llm,
            "llm_error": trace.llm_error,
            "error": trace.error,
            "created_at": trace.created_at or utcnow(),
        }
        statement = self._insert(TraceRow.__table__).values(**values)
        replaced = {k: statement.excluded[k] for k in values if k not in ("trace_id", "created_at")}
        async with self._session() as s:
            await s.execute(statement.on_conflict_do_update(index_elements=["trace_id"], set_=replaced))

    async def get_trace(self, trace_id: str, owner_id: str) -> Trace | None:
        async with self._session() as s:
            row = await s.scalar(
                select(TraceRow)
                .join(ConversationRow, ConversationRow.id == TraceRow.conversation_id)
                .where(TraceRow.trace_id == trace_id, ConversationRow.owner_id == owner_id)
            )
            return _trace(row) if row else None


class SqlTraceRepository:
    """The TraceRepository view of the same store (its `get` would clash with the conversations' `get`)."""

    def __init__(self, chats: SqlChatRepository):
        self._chats = chats

    async def save(self, trace: Trace) -> None:
        await self._chats.save(trace)

    async def get(self, trace_id: str, owner_id: str) -> Trace | None:
        return await self._chats.get_trace(trace_id, owner_id)


def _title(title: str | None) -> str | None:
    return title[:MAX_TITLE] if title is not None else None


def _conversation(row: ConversationRow, messages: list[Message] | None = None) -> Conversation:
    settings = row.settings or {}
    return Conversation(
        id=row.id,
        owner_id=row.owner_id,
        title=row.title,
        settings=ChatSettings(provider=settings.get("provider"), model=settings.get("model")),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        messages=tuple(messages or ()),
    )


def _message(row: MessageRow) -> Message:
    feedback = Feedback(row.feedback_value, row.feedback_comment) if row.feedback_value is not None else None
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        created_at=_utc(row.created_at),
        trace_id=row.trace_id,
        feedback=feedback,
    )


def _trace(row: TraceRow) -> Trace:
    return Trace(
        trace_id=row.trace_id,
        conversation_id=row.conversation_id,
        user_message_id=row.user_message_id,
        answer_message_id=row.answer_message_id,
        outcome=Outcome(row.outcome) if row.outcome else None,
        steps=list(row.steps or []),
        tool_calls=list(row.tool_calls or []),
        citations=list(row.citations or []),
        verifier_rounds=row.verifier_rounds,
        usage=Usage(row.input_tokens, row.output_tokens),
        latency_ms=row.latency_ms,
        llm=row.llm,
        llm_error=row.llm_error,
        error=row.error,
        created_at=_utc(row.created_at),
    )
