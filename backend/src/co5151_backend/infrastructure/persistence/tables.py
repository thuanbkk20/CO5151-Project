"""Tables of the chat history. Portable types only (String, Text, Integer, DateTime, JSON): SQLite and PostgreSQL."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ID = String(36)  # UUID text


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON, datetime: DateTime(timezone=True)}


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(32))
    feedback_value: Mapped[int | None] = mapped_column(Integer)
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]


class TraceRow(Base):
    """One answer: what the Advisor did and what it cost."""

    __tablename__ = "traces"
    __table_args__ = (Index("ix_traces_conversation_created", "conversation_id", "created_at"),)

    trace_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    user_message_id: Mapped[str | None] = mapped_column(ID)
    answer_message_id: Mapped[str | None] = mapped_column(ID)
    outcome: Mapped[str | None] = mapped_column(String(16))
    steps: Mapped[list[str]] = mapped_column(default=list)
    tool_calls: Mapped[list[str]] = mapped_column(default=list)
    citations: Mapped[list[str]] = mapped_column(default=list)
    verifier_rounds: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    llm: Mapped[str | None] = mapped_column(String(255))
    llm_error: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
