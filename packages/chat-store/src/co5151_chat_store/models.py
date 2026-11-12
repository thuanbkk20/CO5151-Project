"""Tables of the chat store. Every name starts with `chat_` so the store can share a database with other services.

Only portable SQLAlchemy types are used (String, Text, Integer, Boolean, DateTime, JSON), so the same tables work on
SQLite and on a database server such as PostgreSQL or MySQL.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ID = String(36)  # UUID text; Chainlit ids are UUIDs


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON, datetime: DateTime(timezone=True)}


class UserRow(Base):
    __tablename__ = "chat_users"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    identifier: Mapped[str] = mapped_column(String(255), unique=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    created_at: Mapped[datetime]


class ConversationRow(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (Index("ix_chat_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("chat_users.id"))
    title: Mapped[str | None] = mapped_column(String(255))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    tags: Mapped[list[str]] = mapped_column(default=list)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class StepRow(Base):
    """A message or an intermediate step shown in the chat (user message, answer, "Chi tiết xử lý"...)."""

    __tablename__ = "chat_steps"
    __table_args__ = (Index("ix_chat_steps_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"))
    parent_id: Mapped[str | None] = mapped_column(ID)
    type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255), default="")
    input: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    # Display options of the UI (showInput, language, ...), kept as given
    display: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime]
    start_at: Mapped[datetime | None]
    end_at: Mapped[datetime | None]


class TurnRow(Base):
    """One question and its answer, identified by a trace id: what the Advisor did and what it cost."""

    __tablename__ = "chat_turns"
    __table_args__ = (Index("ix_chat_turns_conversation_created", "conversation_id", "created_at"),)

    trace_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"))
    user_message_id: Mapped[str | None] = mapped_column(ID)
    answer_message_id: Mapped[str | None] = mapped_column(ID)
    outcome: Mapped[str | None] = mapped_column(String(32))
    tool_calls: Mapped[list[str]] = mapped_column(default=list)
    citations: Mapped[list[str]] = mapped_column(default=list)
    verifier_rounds: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    llm: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]


class FeedbackRow(Base):
    __tablename__ = "chat_feedback"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    step_id: Mapped[str] = mapped_column(ID, unique=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("chat_conversations.id"))
    value: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
