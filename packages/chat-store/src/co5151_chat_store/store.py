import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, event, func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, ConversationRow, FeedbackRow, StepRow, TurnRow, UserRow
from .records import Conversation, Feedback, Page, Step, Turn, User

MAX_TITLE = 255


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite gives back naive datetimes; every value is stored in UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def create_engine(url: str) -> AsyncEngine:
    """An async engine for `url`. A SQLite file gets its folder created and foreign keys enforced."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
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
    """Conversations of each user, their messages, and one trace per answer.

    All methods are async and take plain values or the dataclasses of `records`, so callers never see SQLAlchemy.
    Swap the database by changing the URL only.
    """

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
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

    # Users ---------------------------------------------------------------------------------------------------

    async def get_user(self, identifier: str) -> User | None:
        async with self._session() as s:
            row = await s.scalar(select(UserRow).where(UserRow.identifier == identifier))
            return _user(row) if row else None

    async def get_or_create_user(self, identifier: str, metadata: dict[str, Any] | None = None) -> User:
        async with self._session() as s:
            row = await s.scalar(select(UserRow).where(UserRow.identifier == identifier))
            if row is None:
                row = UserRow(id=str(uuid.uuid4()), identifier=identifier, meta=metadata or {}, created_at=utcnow())
                s.add(row)
            elif metadata is not None:
                row.meta = metadata
            return _user(row)

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
        """Create the conversation or update the fields that are given; `None` leaves a field as it is."""
        async with self._session() as s:
            row = await _conversation_row(s, conversation_id)
            if user_id is not None:
                row.user_id = user_id
            if title is not None:
                row.title = title[:MAX_TITLE]
            if metadata is not None:
                row.meta = {**(row.meta or {}), **metadata}
            if tags is not None:
                row.tags = tags
            row.updated_at = utcnow()

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

    async def upsert_step(self, step: Step) -> None:
        """Insert the step, or replace it if it exists. The conversation is created if needed and marked active."""
        async with self._session() as s:
            conversation = await _conversation_row(s, step.conversation_id)
            conversation.updated_at = utcnow()
            await s.flush()  # the conversation must exist before the step that points to it
            await s.merge(
                StepRow(
                    id=step.id,
                    conversation_id=step.conversation_id,
                    parent_id=step.parent_id,
                    type=step.type,
                    name=step.name,
                    input=step.input,
                    output=step.output,
                    is_error=step.is_error,
                    meta=step.metadata,
                    display=step.display,
                    created_at=step.created_at,
                    start_at=step.start_at,
                    end_at=step.end_at,
                )
            )

    async def delete_step(self, step_id: str) -> None:
        async with self._session() as s:
            await s.execute(delete(FeedbackRow).where(FeedbackRow.step_id == step_id))
            await s.execute(delete(StepRow).where(StepRow.id == step_id))

    # Feedback ------------------------------------------------------------------------------------------------

    async def upsert_feedback(self, feedback: Feedback) -> str:
        """One feedback per step: a new one replaces the previous. Returns the id of the stored feedback."""
        async with self._session() as s:
            row = await s.scalar(select(FeedbackRow).where(FeedbackRow.step_id == feedback.step_id))
            conversation_id = await s.scalar(select(StepRow.conversation_id).where(StepRow.id == feedback.step_id))
            if row is None:
                row = FeedbackRow(id=feedback.id, step_id=feedback.step_id, created_at=utcnow())
                s.add(row)
            row.value, row.comment, row.conversation_id = feedback.value, feedback.comment, conversation_id
            return row.id

    async def delete_feedback(self, feedback_id: str) -> bool:
        async with self._session() as s:
            result = await s.execute(delete(FeedbackRow).where(FeedbackRow.id == feedback_id))
            return bool(result.rowcount)

    # Turns ---------------------------------------------------------------------------------------------------

    async def record_turn(self, turn: Turn) -> None:
        async with self._session() as s:
            await _conversation_row(s, turn.conversation_id)
            await s.flush()
            values = {f.name: getattr(turn, f.name) for f in fields(Turn)}
            values["created_at"] = turn.created_at or utcnow()
            await s.merge(TurnRow(**values))

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


async def _conversation_row(s: AsyncSession, conversation_id: str) -> ConversationRow:
    row = await s.get(ConversationRow, conversation_id)
    if row is None:
        now = utcnow()
        row = ConversationRow(id=conversation_id, meta={}, tags=[], created_at=now, updated_at=now)
        s.add(row)
    return row


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
