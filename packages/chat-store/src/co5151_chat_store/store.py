"""Chat store: conversations of each user, their messages, and one trace per answer.

Design rules, each one fixing a failure seen in practice:

- Every write that can create a conversation takes its owner, so no code path leaves a conversation without one.
  An owner is only set while it is empty and never replaced, so a conversation cannot change hands.
- Creating a row is a single `INSERT ... ON CONFLICT` statement, never "read, then insert if missing": the chat UI
  writes the first message and creates the thread concurrently, and both must succeed.
- Only SQLite and PostgreSQL are accepted: they are the two databases these statements are written and tested for.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Table, and_, delete, event, func, or_, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, ConversationRow, FeedbackRow, StepRow, TurnRow, UserRow
from .records import Conversation, Feedback, Page, Step, Turn, User

MAX_TITLE = 255
SUPPORTED_BACKENDS = ("sqlite", "postgresql")
_INSERT = {"sqlite": sqlite.insert, "postgresql": postgresql.insert}


class UnsupportedDatabase(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
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


class ChatStore:
    """All methods are async and take plain values or the dataclasses of `records`; callers never see SQLAlchemy."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.backend = engine.dialect.name
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str) -> "ChatStore":
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

    def _insert(self, table: Table):
        return _INSERT[self.backend](table)

    async def _ensure_conversation(self, s: AsyncSession, conversation_id: str, owner_id: str | None) -> None:
        """Create the conversation if missing, and give it `owner_id` if it has no owner yet. Never changes an owner."""
        now = utcnow()
        await s.execute(
            self._insert(ConversationRow.__table__)
            .values(id=conversation_id, user_id=owner_id, metadata={}, tags=[], created_at=now, updated_at=now)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        if owner_id is not None:
            await s.execute(
                update(ConversationRow)
                .where(ConversationRow.id == conversation_id, ConversationRow.user_id.is_(None))
                .values(user_id=owner_id)
            )

    # Users ---------------------------------------------------------------------------------------------------

    async def get_user(self, identifier: str) -> User | None:
        async with self._session() as s:
            row = await s.scalar(select(UserRow).where(UserRow.identifier == identifier))
            return _user(row) if row else None

    async def get_or_create_user(self, identifier: str, metadata: dict[str, Any] | None = None) -> User:
        async with self._session() as s:
            await s.execute(
                self._insert(UserRow.__table__)
                .values(id=str(uuid.uuid4()), identifier=identifier, metadata=metadata or {}, created_at=utcnow())
                .on_conflict_do_nothing(index_elements=["identifier"])
            )
            if metadata is not None:
                await s.execute(update(UserRow).where(UserRow.identifier == identifier).values(meta=metadata))
            return _user(await s.scalar(select(UserRow).where(UserRow.identifier == identifier)))

    # Conversations -------------------------------------------------------------------------------------------

    async def upsert_conversation(
        self,
        conversation_id: str,
        *,
        user_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Create the conversation or update the given fields; `None` leaves a field as it is.

        `user_id` only takes effect while the conversation has no owner.
        """
        async with self._session() as s:
            await self._ensure_conversation(s, conversation_id, user_id)
            values: dict[str, Any] = {"updated_at": utcnow()}
            if title is not None:
                values["title"] = title[:MAX_TITLE]
            if tags is not None:
                values["tags"] = tags
            if metadata is not None:
                current = await s.scalar(select(ConversationRow.meta).where(ConversationRow.id == conversation_id))
                values["meta"] = {**(current or {}), **metadata}
            await s.execute(update(ConversationRow).where(ConversationRow.id == conversation_id).values(**values))

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """The conversation with its steps in order, each step carrying its feedback."""
        async with self._session() as s:
            found = (
                await s.execute(
                    select(ConversationRow, UserRow.identifier)
                    .outerjoin(UserRow, ConversationRow.user_id == UserRow.id)
                    .where(ConversationRow.id == conversation_id)
                )
            ).first()
            if found is None:
                return None
            row, identifier = found
            steps = (
                await s.scalars(
                    select(StepRow)
                    .where(StepRow.conversation_id == conversation_id)
                    .order_by(StepRow.created_at, StepRow.id)
                )
            ).all()
            feedback = {
                f.step_id: _feedback(f)
                for f in await s.scalars(select(FeedbackRow).where(FeedbackRow.conversation_id == conversation_id))
            }
            conversation = _conversation(row, identifier)
            conversation.steps = [_step(step, feedback.get(step.id)) for step in steps]
            return conversation

    async def conversation_owner(self, conversation_id: str) -> str | None:
        """Identifier of the user who owns the conversation, or None if it has no owner or does not exist."""
        async with self._session() as s:
            return await s.scalar(
                select(UserRow.identifier)
                .join(ConversationRow, ConversationRow.user_id == UserRow.id)
                .where(ConversationRow.id == conversation_id)
            )

    async def list_conversations(
        self, user_id: str, *, limit: int = 20, cursor: str | None = None, search: str | None = None
    ) -> Page:
        """The user's conversations, most recently active first. `cursor` is the id of the last one already shown."""
        async with self._session() as s:
            query = select(ConversationRow, UserRow.identifier).join(UserRow, ConversationRow.user_id == UserRow.id)
            query = query.where(ConversationRow.user_id == user_id)
            if search:
                query = query.where(func.lower(ConversationRow.title).contains(search.lower()))
            if cursor and (last := await s.get(ConversationRow, cursor)) is not None:
                query = query.where(
                    or_(
                        ConversationRow.updated_at < last.updated_at,
                        and_(ConversationRow.updated_at == last.updated_at, ConversationRow.id < last.id),
                    )
                )
            query = query.order_by(ConversationRow.updated_at.desc(), ConversationRow.id.desc()).limit(limit + 1)
            rows = (await s.execute(query)).all()
            return Page([_conversation(r, i) for r, i in rows[:limit]], has_next=len(rows) > limit)

    async def delete_conversation(self, conversation_id: str) -> None:
        async with self._session() as s:
            for table in (FeedbackRow, TurnRow, StepRow):
                await s.execute(delete(table).where(table.conversation_id == conversation_id))
            await s.execute(delete(ConversationRow).where(ConversationRow.id == conversation_id))

    # Steps ---------------------------------------------------------------------------------------------------

    async def upsert_step(self, step: Step, *, owner_id: str | None = None) -> None:
        """Insert the step, or replace it if it exists; its conversation is created for `owner_id` if needed."""
        values = {
            "id": step.id,
            "conversation_id": step.conversation_id,
            "parent_id": step.parent_id,
            "type": step.type,
            "name": step.name,
            "input": step.input,
            "output": step.output,
            "is_error": step.is_error,
            "metadata": step.metadata,
            "display": step.display,
            "created_at": step.created_at,
            "start_at": step.start_at,
            "end_at": step.end_at,
        }
        statement = self._insert(StepRow.__table__).values(**values)
        replaced = {k: statement.excluded[k] for k in values if k not in ("id", "conversation_id", "created_at")}
        async with self._session() as s:
            await self._ensure_conversation(s, step.conversation_id, owner_id)
            await s.execute(statement.on_conflict_do_update(index_elements=["id"], set_=replaced))
            await s.execute(
                update(ConversationRow).where(ConversationRow.id == step.conversation_id).values(updated_at=utcnow())
            )

    async def delete_step(self, step_id: str) -> None:
        async with self._session() as s:
            await s.execute(delete(FeedbackRow).where(FeedbackRow.step_id == step_id))
            await s.execute(delete(StepRow).where(StepRow.id == step_id))

    # Feedback ------------------------------------------------------------------------------------------------

    async def upsert_feedback(self, feedback: Feedback) -> str:
        """One feedback per step: a new one replaces the previous. Returns the id of the stored feedback."""
        conversation_id = select(StepRow.conversation_id).where(StepRow.id == feedback.step_id).scalar_subquery()
        statement = self._insert(FeedbackRow.__table__).values(
            id=feedback.id,
            step_id=feedback.step_id,
            conversation_id=conversation_id,
            value=feedback.value,
            comment=feedback.comment,
            created_at=utcnow(),
        )
        async with self._session() as s:
            await s.execute(
                statement.on_conflict_do_update(
                    index_elements=["step_id"],
                    set_={"value": statement.excluded.value, "comment": statement.excluded.comment},
                )
            )
            return await s.scalar(select(FeedbackRow.id).where(FeedbackRow.step_id == feedback.step_id))

    async def delete_feedback(self, feedback_id: str) -> bool:
        async with self._session() as s:
            result = await s.execute(delete(FeedbackRow).where(FeedbackRow.id == feedback_id))
            return bool(result.rowcount)

    # Turns ---------------------------------------------------------------------------------------------------

    async def record_turn(self, turn: Turn, *, owner_id: str | None = None) -> None:
        values = {f.name: getattr(turn, f.name) for f in fields(Turn)}
        values["created_at"] = turn.created_at or utcnow()
        statement = self._insert(TurnRow.__table__).values(**values)
        async with self._session() as s:
            await self._ensure_conversation(s, turn.conversation_id, owner_id)
            await s.execute(
                statement.on_conflict_do_update(
                    index_elements=["trace_id"],
                    set_={k: statement.excluded[k] for k in values if k not in ("trace_id", "created_at")},
                )
            )

    async def list_turns(self, conversation_id: str) -> list[Turn]:
        async with self._session() as s:
            rows = await s.scalars(
                select(TurnRow).where(TurnRow.conversation_id == conversation_id).order_by(TurnRow.created_at)
            )
            return [_turn(row) for row in rows]

    async def get_turn(self, trace_id: str) -> Turn | None:
        async with self._session() as s:
            row = await s.get(TurnRow, trace_id)
            return _turn(row) if row else None


def _user(row: UserRow) -> User:
    return User(id=row.id, identifier=row.identifier, created_at=as_utc(row.created_at), metadata=row.meta or {})


def _conversation(row: ConversationRow, identifier: str | None) -> Conversation:
    return Conversation(
        id=row.id,
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
        user_id=row.user_id,
        user_identifier=identifier,
        title=row.title,
        metadata=row.meta or {},
        tags=row.tags or [],
    )


def _step(row: StepRow, feedback: Feedback | None) -> Step:
    return Step(
        id=row.id,
        conversation_id=row.conversation_id,
        type=row.type,
        created_at=as_utc(row.created_at),
        name=row.name,
        input=row.input,
        output=row.output,
        parent_id=row.parent_id,
        is_error=row.is_error,
        metadata=row.meta or {},
        display=row.display or {},
        start_at=as_utc(row.start_at),
        end_at=as_utc(row.end_at),
        feedback=feedback,
    )


def _feedback(row: FeedbackRow) -> Feedback:
    return Feedback(id=row.id, step_id=row.step_id, value=row.value, comment=row.comment)


def _turn(row: TurnRow) -> Turn:
    values = {f.name: getattr(row, f.name) for f in fields(Turn)}
    values["created_at"] = as_utc(row.created_at)
    return Turn(**values)
