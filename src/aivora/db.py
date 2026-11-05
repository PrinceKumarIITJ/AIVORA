import time
import uuid
from pathlib import Path

from sqlalchemy import (Boolean, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    industry: Mapped[str] = mapped_column(String(80), default="General")
    assistant_name: Mapped[str] = mapped_column(String(60), default="AIVORA")
    guidance: Mapped[str] = mapped_column(Text, default="Be clear, helpful and concise.")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="employee")
    department: Mapped[str] = mapped_column(String(60), default="General")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256 only
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(String(80), default="Browser")
    scopes: Mapped[str] = mapped_column(Text, default="[]")
    csrf: Mapped[str] = mapped_column(String(64), default="")
    expires: Mapped[float] = mapped_column(Float)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20))
    department: Mapped[str] = mapped_column(String(60))
    expires: Mapped[float] = mapped_column(Float)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(20), default="organization")
    department: Mapped[str] = mapped_column(String(60), default="General")
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[str] = mapped_column(Text, default="[]")
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Workflow(Base):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(String(60), default="General")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("org_id", "user_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    expires: Mapped[float] = mapped_column(Float)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="reserved")
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    retrieved: Mapped[int] = mapped_column(Integer, default=0)
    stages: Mapped[str] = mapped_column(Text, default="[]")
    created: Mapped[float] = mapped_column(Float, default=time.time)


class DailyQuota(Base):
    __tablename__ = "daily_quotas"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    day: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36))
    event: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(100), default="")
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Automation(Base):
    __tablename__ = "automations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    interval_hours: Mapped[int] = mapped_column(Integer)
    next_run: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (UniqueConstraint("automation_id", "scheduled_for"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    automation_id: Mapped[str] = mapped_column(ForeignKey("automations.id"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    scheduled_for: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("org_id", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str] = mapped_column(String(36))
    dedupe_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created: Mapped[float] = mapped_column(Float, default=time.time)


def database(url):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///./"):
            Path(url.removeprefix("sqlite:///./")).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)
