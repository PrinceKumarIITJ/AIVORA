"""Durable multi-agent execution: SQL checkpoints, leases and a configurable LangGraph DAG."""

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from langsmith import tracing_context
from sqlalchemy import select, update

from ..db import Chunk, DailyQuota, Document, User, Workflow, uid
from ..retrieval import retrieve, visible
from ..security import audit
from . import agents
from .connectors import allowed, read_context
from .contracts import DEFAULT_TEAM, AgentOutput, TeamDefinition
from .data import dataset_visible, profile
from .model_config import resolve_settings
from .models import (
    AgentArtifact,
    AgentStep,
    AgentTeam,
    Connector,
    Dataset,
    Mission,
    MissionEvent,
    Operation,
)


class MissionBlocked(agents.AgentError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def event(db, mission, name, agent_id="", detail=""):
    db.add(
        MissionEvent(
            org_id=mission.org_id,
            mission_id=mission.id,
            event=name,
            agent_id=agent_id,
            detail=detail[:300],
        )
    )


def default_team(db, org_id):
    team_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "aivora-default-team:" + org_id))
    if db.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    db.execute(
        insert(AgentTeam)
        .values(
            id=team_id,
            org_id=org_id,
            name=DEFAULT_TEAM.name,
            description=DEFAULT_TEAM.description,
            definition=DEFAULT_TEAM.definition.model_dump_json(),
            revision=1,
            created=time.time(),
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return db.get(AgentTeam, team_id)


def context_valid(db, user, context):
    if not user or not user.active:
        return False
    for item in context["evidence"]:
        if item["type"] == "document":
            row = db.execute(
                select(Chunk, Document)
                .join(Document)
                .where(Chunk.id == item["id"], Document.org_id == user.org_id, visible(user))
            ).first()
            if not row or row[1].version != item["version"]:
                return False
        elif item["type"] == "dataset":
            value = db.scalar(
                select(Dataset).where(
                    Dataset.id == item["resource_id"],
                    Dataset.org_id == user.org_id,
                    dataset_visible(user),
                )
            )
            if not value or value.content_hash != item["hash"]:
                return False
        else:
            value = db.get(Connector, item["resource_id"])
            if not value or not allowed(value, user) or value.revision != item["revision"]:
                return False
    return True


def prepare_context(db, user, body, settings):
    evidence = [
        {
            "id": s["chunk_id"],
            "resource_id": s["document_id"],
            "type": "document",
            "title": s["title"],
            "version": s["version"],
            "page": s["page"],
            "text": s["text"],
        }
        for s in retrieve(db, user, body.objective, settings.semantic_model, limit=7)
    ]
    for dataset_id in dict.fromkeys(body.dataset_ids):
        value = db.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id, Dataset.org_id == user.org_id, dataset_visible(user)
            )
        )
        if not value:
            raise MissionBlocked("dataset_not_accessible")
        columns, rows = json.loads(value.columns_json), json.loads(value.rows_json)
        computed = profile(columns, rows, body.group_by, body.metric)
        evidence.append(
            {
                "id": "dataset:" + value.id,
                "resource_id": value.id,
                "type": "dataset",
                "title": value.title,
                "hash": value.content_hash,
                "profile": computed,
            }
        )
    connectors = []
    for connector_id in dict.fromkeys(body.connector_ids):
        value = db.get(Connector, connector_id)
        if not value or not allowed(value, user):
            raise MissionBlocked("connector_not_accessible")
        evidence.append(
            {
                "id": "connector:" + value.id,
                "resource_id": value.id,
                "type": "connector",
                "title": value.name,
                "revision": value.revision,
                "data": read_context(settings, value),
            }
        )
        connectors.append(
            {
                "id": value.id,
                "name": value.name,
                "kind": value.kind,
                "revision": value.revision,
                "department": value.department,
            }
        )
    departments = sorted(
        set(db.scalars(select(User.department).where(User.org_id == user.org_id)))
        | set(db.scalars(select(Workflow.department).where(Workflow.org_id == user.org_id)))
        | {"General"}
    )
    return {
        "evidence": evidence,
        "connectors": connectors,
        "departments": [user.department] + [d for d in departments if d != user.department],
    }


def create_mission(db, user, body, settings):
    settings, model_identity = resolve_settings(db, settings, user.org_id)
    fingerprint = hashlib.sha256(
        json.dumps(body.model_dump(exclude={"request_key"}), sort_keys=True).encode()
    ).hexdigest()
    previous = db.scalar(
        select(Mission).where(
            Mission.org_id == user.org_id,
            Mission.user_id == user.id,
            Mission.request_key == body.request_key,
        )
    )
    if previous:
        if json.loads(previous.context_json).get("request_fingerprint") != fingerprint:
            raise MissionBlocked("request_key_conflict")
        return previous
    if body.mode == "ai" and (
        settings.provider not in {"groq", "gemini"}
        or not settings.model
        or not (settings.groq_key if settings.provider == "groq" else settings.google_key)
    ):
        raise MissionBlocked("provider_not_configured")
    team = (
        default_team(db, user.org_id)
        if body.team_id == "default"
        else db.scalar(
            select(AgentTeam).where(AgentTeam.id == body.team_id, AgentTeam.org_id == user.org_id)
        )
    )
    if not team:
        raise MissionBlocked("team_not_accessible")
    definition = TeamDefinition.model_validate_json(team.definition)
    context = prepare_context(db, user, body, settings)
    context["model_identity"] = model_identity
    context["request_fingerprint"] = fingerprint
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    if db.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    db.execute(
        insert(DailyQuota)
        .values(user_id=user.id, day=day, count=0)
        .on_conflict_do_nothing(index_elements=["user_id", "day"])
    )
    if not db.execute(
        update(DailyQuota)
        .where(
            DailyQuota.user_id == user.id,
            DailyQuota.day == day,
            DailyQuota.count < settings.daily_limit,
        )
        .values(count=DailyQuota.count + 1)
    ).rowcount:
        raise MissionBlocked("daily_limit_reached")
    mission = Mission(
        org_id=user.org_id,
        user_id=user.id,
        team_id=team.id,
        title=body.title,
        objective=body.objective,
        context_json=json.dumps(context, ensure_ascii=False),
        team_snapshot=definition.model_dump_json(),
        request_key=body.request_key,
        mode=body.mode,
        max_tokens=body.max_tokens,
    )
    db.add(mission)
    db.flush()
    db.add_all(
        [
            AgentStep(org_id=user.org_id, mission_id=mission.id, agent_id=a.id, role=a.role)
            for a in definition.agents
        ]
    )
    event(db, mission, "mission.queued")
    audit(db, user, "mission.created", mission.id)
    return mission


def merge_results(left, right):
    return {**left, **right}


class TeamState(TypedDict):
    results: Annotated[dict, merge_results]


def check_lease(db, mission_id, lease):
    mission = db.get(Mission, mission_id)
    if (
        not mission
        or mission.status != "running"
        or mission.lease_id != lease
        or mission.lease_until < time.time()
    ):
        raise MissionBlocked("mission_lease_lost")
    user = db.get(User, mission.user_id)
    if not context_valid(db, user, json.loads(mission.context_json)):
        raise MissionBlocked("source_access_changed")
    return mission, user


def apply_read_requests(db, mission, user, output, settings):
    context = json.loads(mission.context_json)
    known = {e["id"] for e in context["evidence"]}
    for request in output.tool_requests:
        if request.tool == "knowledge.search":
            for source in retrieve(db, user, request.query, settings.semantic_model, limit=3):
                if source["chunk_id"] in known:
                    continue
                if len([e for e in context["evidence"] if e["type"] == "document"]) >= 12:
                    break
                context["evidence"].append(
                    {
                        "id": source["chunk_id"],
                        "resource_id": source["document_id"],
                        "type": "document",
                        "title": source["title"],
                        "version": source["version"],
                        "page": source["page"],
                        "text": source["text"],
                    }
                )
                known.add(source["chunk_id"])
        else:
            evidence = next(
                (
                    e
                    for e in context["evidence"]
                    if e["type"] == "dataset" and e["resource_id"] == request.dataset_id
                ),
                None,
            )
            value = db.scalar(
                select(Dataset).where(
                    Dataset.id == request.dataset_id,
                    Dataset.org_id == user.org_id,
                    dataset_visible(user),
                )
            )
            if not value or not evidence:
                raise MissionBlocked("dataset_not_accessible")
            calculated = profile(
                json.loads(value.columns_json),
                json.loads(value.rows_json),
                request.group_by,
                request.metric,
            )
            evidence.setdefault("agent_analyses", []).append(calculated)
        event(db, mission, "tool.completed", detail=request.tool)
    mission.context_json = json.dumps(context, ensure_ascii=False)


def execute_step(factory, settings, mission_id, lease, agent, outputs):
    with factory.begin() as db:
        mission, user = check_lease(db, mission_id, lease)
        step = db.scalar(
            select(AgentStep).where(
                AgentStep.mission_id == mission_id, AgentStep.agent_id == agent.id
            )
        )
        if step.status == "completed":
            return json.loads(step.output_json)
        if step.attempts >= 3:
            raise MissionBlocked("agent_retry_limit")
        context = json.loads(mission.context_json)
        prior_error = (
            db.scalar(
                select(MissionEvent.detail)
                .where(
                    MissionEvent.mission_id == mission_id,
                    MissionEvent.agent_id == agent.id,
                    MissionEvent.event == "agent.failed",
                )
                .order_by(MissionEvent.created.desc())
                .limit(1)
            )
            if step.attempts
            else ""
        )
        effective, identity = resolve_settings(db, settings, user.org_id)
        if mission.mode == "ai" and identity != context["model_identity"]:
            raise MissionBlocked("model_configuration_changed")
        payload = {
            "objective": mission.objective,
            "validation_feedback": prior_error or "",
            "agent_task": agent.instructions,
            "evidence": context["evidence"],
            "departments": context["departments"],
            "connectors": context["connectors"],
            "previous_outputs": {
                key: {
                    "summary": value["summary"][:900],
                    "findings": [
                        {**f, "statement": f["statement"][:400]}
                        for f in value.get("findings", [])[:3]
                    ],
                    "actions": [
                        {**a, "description": a["description"][:500]}
                        for a in value.get("actions", [])
                    ],
                    "risks": [r[:200] for r in value.get("risks", [])],
                    "questions": value.get("questions", [])[:3],
                    "verdict": value["verdict"],
                }
                for key, value in outputs.items()
            },
            "human_feedback": context.get("human_feedback", []),
            "document_catalog": [
                {"title": d.title, "id": d.id}
                for d in db.scalars(
                    select(Document).where(Document.org_id == user.org_id, visible(user)).limit(40)
                )
            ]
            if agent.role == "coordinator"
            else [],
        }
        if agent.role == "researcher":
            payload["evidence"] = [
                e for e in payload["evidence"] if e["type"] in {"document", "connector"}
            ]
        if agent.role == "analyst":
            payload["evidence"] = [
                e for e in payload["evidence"] if e["type"] in {"dataset", "connector"}
            ]
        # Bound accumulated cross-agent context independently of model context limits.
        for output in payload["previous_outputs"].values():
            if len(json.dumps(output)) > 18000:
                raise MissionBlocked("agent_context_limit")
        reserve = len(json.dumps(payload, ensure_ascii=False).encode()) + 7000
        if mission.mode == "ai":
            reserved = db.execute(
                update(Mission)
                .where(
                    Mission.id == mission_id,
                    Mission.lease_id == lease,
                    Mission.reserved_tokens + reserve <= Mission.max_tokens,
                    Mission.model_calls < 20,
                )
                .values(
                    reserved_tokens=Mission.reserved_tokens + reserve,
                    model_calls=Mission.model_calls + 1,
                )
            ).rowcount
            if not reserved:
                raise MissionBlocked("mission_budget_exhausted")
        step.status, step.started, step.attempts = "running", time.time(), step.attempts + 1
        event(db, mission, "agent.started", agent.id)
        mode = mission.mode
    try:
        output, tokens = (
            agents.complete_agent(effective, agent, payload)
            if mode == "ai"
            else agents.evidence_agent(agent, payload)
        )
        agents.validate_output(output, agent, payload)
        with factory.begin() as db:
            mission, user = check_lease(db, mission_id, lease)
            if output.tool_requests:
                apply_read_requests(db, mission, user, output, effective)
            step = db.scalar(
                select(AgentStep).where(
                    AgentStep.mission_id == mission_id, AgentStep.agent_id == agent.id
                )
            )
            step.status, step.completed = "completed", time.time()
            step.output_json = output.model_dump_json()
            db.add(
                AgentArtifact(
                    org_id=mission.org_id,
                    mission_id=mission_id,
                    agent_id=agent.id,
                    iteration=mission.iteration,
                    output_json=step.output_json,
                    content_hash=hashlib.sha256(step.output_json.encode()).hexdigest(),
                )
            )
            step.evidence_json = json.dumps([item["id"] for item in payload["evidence"]])
            step.input_tokens, step.output_tokens = tokens
            db.execute(
                update(Mission)
                .where(Mission.id == mission_id, Mission.lease_id == lease)
                .values(
                    input_tokens=Mission.input_tokens + tokens[0],
                    output_tokens=Mission.output_tokens + tokens[1],
                    lease_until=time.time() + 300,
                    updated=time.time(),
                )
            )
            event(db, mission, "agent.completed", agent.id)
        return output.model_dump()
    except Exception as error:
        with factory.begin() as db:
            mission = db.get(Mission, mission_id)
            if mission and mission.lease_id == lease:
                step = db.scalar(
                    select(AgentStep).where(
                        AgentStep.mission_id == mission_id, AgentStep.agent_id == agent.id
                    )
                )
                if step.status != "completed":
                    deferred = isinstance(error, agents.ProviderRateLimit)
                    step.status = "queued" if deferred else "failed"
                    if deferred:
                        step.attempts = max(0, step.attempts - 1)
                        db.execute(
                            update(Mission)
                            .where(Mission.id == mission_id, Mission.lease_id == lease)
                            .values(
                                reserved_tokens=Mission.reserved_tokens - reserve,
                                model_calls=Mission.model_calls - 1,
                            )
                        )
                    detail = (
                        str(error)
                        if isinstance(error, agents.AgentError)
                        else "Processing failed; no output was published"
                    )
                    event(
                        db,
                        mission,
                        "agent.deferred" if deferred else "agent.failed",
                        agent.id,
                        detail,
                    )
        raise


def process_mission(factory, settings, mission_id):
    lease = uid()
    with factory.begin() as db:
        claimed = db.execute(
            update(Mission)
            .where(
                Mission.id == mission_id,
                (Mission.status == "queued")
                | (
                    (Mission.status.in_(["running", "waiting_provider"]))
                    & (Mission.lease_until < time.time())
                ),
            )
            .values(
                status="running",
                lease_id=lease,
                lease_until=time.time() + 300,
                updated=time.time(),
                error_code="",
            )
        ).rowcount
        if not claimed:
            return False
        mission = db.get(Mission, mission_id)
        definition = TeamDefinition.model_validate_json(mission.team_snapshot)
        event(db, mission, "mission.started")
    try:
        builder = StateGraph(TeamState)
        parents = set()
        for agent in definition.agents:

            def node(state, agent=agent):
                output = execute_step(
                    factory, settings, mission_id, lease, agent, dict(state["results"])
                )
                return {"results": {agent.id: output}}

            builder.add_node(
                agent.id,
                node,
                retry_policy=RetryPolicy(
                    max_attempts=3,
                    initial_interval=1,
                    retry_on=lambda error: (
                        isinstance(error, agents.AgentError)
                        and error.code == "provider_contract_error"
                    ),
                ),
            )
            if agent.depends_on:
                builder.add_edge(agent.depends_on, agent.id)
                parents.update(agent.depends_on)
            else:
                builder.add_edge(START, agent.id)
        for agent in definition.agents:
            if agent.id not in parents:
                builder.add_edge(agent.id, END)
        with tracing_context(enabled=False):
            builder.compile().invoke(
                {"results": {}}, config={"recursion_limit": 24, "max_concurrency": 2}
            )
        with factory.begin() as db:
            mission, user = check_lease(db, mission_id, lease)
            steps = list(db.scalars(select(AgentStep).where(AgentStep.mission_id == mission_id)))
            reviewer = next(s for s in steps if s.role == "reviewer")
            review = AgentOutput.model_validate_json(reviewer.output_json)
            # A reviewer cannot be silently bypassed. Owner explicitly submits draft actions later.
            mission.status = "ready" if review.verdict == "pass" else "review_required"
            for step in steps:
                if step.role != "planner":
                    continue
                output = AgentOutput.model_validate_json(step.output_json)
                for index, action in enumerate(output.actions):
                    key = f"{step.agent_id}:r{mission.iteration}:{index}"
                    if db.scalar(
                        select(Operation.id).where(
                            Operation.mission_id == mission_id, Operation.operation_key == key
                        )
                    ):
                        continue
                    arguments = action.model_dump()
                    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
                    connector = (
                        db.get(Connector, action.connector_id) if action.connector_id else None
                    )
                    db.add(
                        Operation(
                            org_id=user.org_id,
                            mission_id=mission_id,
                            requester_id=user.id,
                            operation_key=key,
                            kind=action.kind,
                            title=action.title,
                            arguments_json=canonical,
                            arguments_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                            connector_id=action.connector_id,
                            connector_revision=connector.revision if connector else 0,
                            department=action.department,
                            expires=time.time() + 7 * 86400,
                        )
                    )
            mission.lease_until = 0
            mission.updated = time.time()
            event(db, mission, "mission." + mission.status)
        return True
    except Exception as error:
        code = error.code if isinstance(error, agents.AgentError) else "execution_error"
        with factory.begin() as db:
            mission = db.get(Mission, mission_id)
            if mission and mission.lease_id == lease and mission.status == "running":
                deferred = isinstance(error, agents.ProviderRateLimit)
                mission.status = "waiting_provider" if deferred else "failed"
                mission.error_code = code
                mission.lease_until = time.time() + error.delay if deferred else 0
                mission.updated = time.time()
                event(
                    db, mission, "mission.deferred" if deferred else "mission.failed", detail=code
                )
        return False


def run_queued(factory, settings, limit=2):
    with factory() as db:
        ids = list(
            db.scalars(
                select(Mission.id)
                .where(
                    (Mission.status == "queued")
                    | (
                        (Mission.status.in_(["running", "waiting_provider"]))
                        & (Mission.lease_until < time.time())
                    )
                )
                .order_by(Mission.created)
                .limit(limit)
            )
        )
    return sum(process_mission(factory, settings, item) for item in ids)
