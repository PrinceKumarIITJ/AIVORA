import time

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, uid


class AgentTeam(Base):
    __tablename__ = "agent_teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Dataset(Base):
    __tablename__ = "business_datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    visibility: Mapped[str] = mapped_column(String(20))
    department: Mapped[str] = mapped_column(String(60))
    columns_json: Mapped[str] = mapped_column(Text)
    rows_json: Mapped[str] = mapped_column(Text)
    profile_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Connector(Base):
    __tablename__ = "operation_connectors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    department: Mapped[str] = mapped_column(String(60))
    config_json: Mapped[str] = mapped_column(Text)
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (UniqueConstraint("org_id", "user_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("agent_teams.id"))
    title: Mapped[str] = mapped_column(String(150))
    objective: Mapped[str] = mapped_column(Text)
    context_json: Mapped[str] = mapped_column(Text)
    team_snapshot: Mapped[str] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40), default="queued")
    mode: Mapped[str] = mapped_column(String(20))
    max_tokens: Mapped[int] = mapped_column(Integer)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    lease_id: Mapped[str] = mapped_column(String(36), default="")
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    created: Mapped[float] = mapped_column(Float, default=time.time)
    updated: Mapped[float] = mapped_column(Float, default=time.time)
    outcome: Mapped[str] = mapped_column(Text, default="")
    finished: Mapped[float] = mapped_column(Float, default=0)
    iteration: Mapped[int] = mapped_column(Integer, default=0)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("mission_id", "agent_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    started: Mapped[float] = mapped_column(Float, default=0)
    completed: Mapped[float] = mapped_column(Float, default=0)


class AgentArtifact(Base):
    __tablename__ = "agent_artifact_versions"
    __table_args__ = (UniqueConstraint("mission_id", "agent_id", "iteration"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(40))
    iteration: Mapped[int] = mapped_column(Integer)
    output_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created: Mapped[float] = mapped_column(Float, default=time.time)


class MissionEvent(Base):
    __tablename__ = "mission_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(40), default="")
    event: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(300), default="")
    created: Mapped[float] = mapped_column(Float, default=time.time)


class Operation(Base):
    __tablename__ = "mission_operations"
    __table_args__ = (UniqueConstraint("mission_id", "operation_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    operation_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(150))
    arguments_json: Mapped[str] = mapped_column(Text)
    arguments_hash: Mapped[str] = mapped_column(String(64))
    connector_id: Mapped[str] = mapped_column(String(36), default="")
    connector_revision: Mapped[int] = mapped_column(Integer, default=0)
    department: Mapped[str] = mapped_column(String(60), default="General")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    reviewer_id: Mapped[str] = mapped_column(String(36), default="")
    reviewer_note: Mapped[str] = mapped_column(String(500), default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    expires: Mapped[float] = mapped_column(Float)
    created: Mapped[float] = mapped_column(Float, default=time.time)
    executing_since: Mapped[float] = mapped_column(Float, default=0)


class WorkItem(Base):
    __tablename__ = "operation_work_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    operation_id: Mapped[str] = mapped_column(ForeignKey("mission_operations.id"), unique=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(String(60))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="planned")
    outcome: Mapped[str] = mapped_column(Text, default="")
    updated: Mapped[float] = mapped_column(Float, default=time.time)


class MissionSchedule(Base):
    __tablename__ = "mission_schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    mission_template_json: Mapped[str] = mapped_column(Text)
    interval_hours: Mapped[int] = mapped_column(Integer)
    next_run: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class IncomingHook(Base):
    __tablename__ = "mission_hooks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    template_json: Mapped[str] = mapped_column(Text)
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class HookEvent(Base):
    __tablename__ = "mission_hook_events"
    __table_args__ = (UniqueConstraint("hook_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    hook_id: Mapped[str] = mapped_column(ForeignKey("mission_hooks.id"))
    external_id: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))


class ModelProfile(Base):
    __tablename__ = "organization_model_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
