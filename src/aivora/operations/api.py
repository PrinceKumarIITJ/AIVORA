import hashlib
import hmac
import json
import secrets
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import User
from ..security import audit, authenticate, browser_only, require_role, require_scope
from .connectors import ConnectorError, allowed, decrypt, encrypt, read_context, validate_config
from .contracts import DEFAULT_TEAM, TEMPLATES, Contract, MissionInput, TeamInput
from .data import dataset_visible, read_csv
from .execution import execute_operation, review_allowed, valid_requester
from .model_config import resolve_settings
from .models import (
    AgentArtifact,
    AgentStep,
    AgentTeam,
    Connector,
    Dataset,
    HookEvent,
    IncomingHook,
    Mission,
    MissionEvent,
    MissionSchedule,
    ModelProfile,
    Operation,
    WorkItem,
)
from .runtime import MissionBlocked, context_valid, create_mission, event, process_mission


class ConnectorInput(Contract):
    name: str = Field(min_length=2, max_length=100)
    kind: str = Field(pattern="^(github|slack)$")
    department: str = Field(default="General", min_length=1, max_length=60)
    config: dict[str, str]
    token: str = Field(min_length=8, max_length=2000)


class ModelInput(Contract):
    provider: str = Field(pattern="^(groq|gemini)$")
    model: str = Field(pattern=r"^[A-Za-z0-9._/-]{2,100}$")
    api_key: str = Field(min_length=8, max_length=2000)


class SubmitInput(Contract):
    operation_ids: list[str] = Field(min_length=1, max_length=12)
    acknowledge_review: bool = False


class DecisionInput(Contract):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=500)


class WorkUpdate(Contract):
    status: str = Field(pattern="^(planned|in_progress|blocked|done)$")
    outcome: str = Field(default="", max_length=2000)


class MissionOutcome(Contract):
    outcome: str = Field(min_length=15, max_length=3000)


class Refinement(Contract):
    feedback: str = Field(min_length=15, max_length=2000)


class ScheduleInput(Contract):
    name: str = Field(min_length=2, max_length=100)
    template: MissionInput
    interval_hours: int = Field(ge=1, le=720)


class HookInput(Contract):
    name: str = Field(min_length=2, max_length=100)
    template: MissionInput


class HookPayload(Contract):
    event_id: str = Field(min_length=1, max_length=100)
    context: str = Field(min_length=1, max_length=2000)


def install_operations(app, factory, settings):
    router = APIRouter(prefix="/api/ops", tags=["Multi-agent operations"])

    def session():
        with factory() as db:
            yield db

    def principal(request: Request, db: Session = Depends(session)):
        p = authenticate(request, db, settings)
        require_scope(p, "knowledge:read")
        require_scope(p, "missions:read" if request.method == "GET" else "missions:write")
        return p

    def owner(db, mission_id, user):
        mission = db.scalar(
            select(Mission).where(
                Mission.id == mission_id, Mission.org_id == user.org_id, Mission.user_id == user.id
            )
        )
        if not mission:
            raise HTTPException(404, "Mission not found")
        return mission

    def accessible(db, mission, user):
        return context_valid(db, user, json.loads(mission.context_json))

    def operation_view(db, value, user):
        work = db.scalar(select(WorkItem).where(WorkItem.operation_id == value.id))
        return {
            "id": value.id,
            "mission_id": value.mission_id,
            "kind": value.kind,
            "title": value.title,
            "arguments": json.loads(value.arguments_json),
            "arguments_hash": value.arguments_hash,
            "department": value.department,
            "status": value.status,
            "mine": value.requester_id == user.id,
            "can_review": review_allowed(value, user) and value.status == "pending",
            "result": json.loads(value.result_json),
            "expires": value.expires,
            "reviewer_note": value.reviewer_note,
            "work_status": work.status if work else None,
        }

    def mission_view(db, mission, user, details=False):
        valid = accessible(db, mission, user)
        steps = list(
            db.scalars(
                select(AgentStep)
                .where(AgentStep.mission_id == mission.id)
                .order_by(AgentStep.started, AgentStep.agent_id)
            )
        )
        result = {
            "id": mission.id,
            "team_id": mission.team_id,
            "title": mission.title,
            "objective": mission.objective,
            "status": mission.status,
            "mode": mission.mode,
            "created": mission.created,
            "updated": mission.updated,
            "error_code": mission.error_code,
            "iteration": mission.iteration,
            "retry_at": mission.lease_until if mission.status == "waiting_provider" else None,
            "outcome": mission.outcome,
            "completed_agents": sum(s.status == "completed" for s in steps),
            "total_agents": len(steps),
            "access_valid": valid,
            "input_tokens": mission.input_tokens,
            "output_tokens": mission.output_tokens,
            "reserved_tokens": mission.reserved_tokens,
            "max_tokens": mission.max_tokens,
            "model_calls": mission.model_calls,
        }
        if details:
            names = {a["id"]: a for a in json.loads(mission.team_snapshot)["agents"]}
            result["agents"] = [
                {
                    "id": s.agent_id,
                    "name": names[s.agent_id]["name"],
                    "role": s.role,
                    "depends_on": names[s.agent_id]["depends_on"],
                    "status": s.status,
                    "attempts": s.attempts,
                    "started": s.started,
                    "completed": s.completed,
                    "output": json.loads(s.output_json)
                    if valid and s.status == "completed"
                    else None,
                }
                for s in steps
            ]
            result["events"] = [
                {"event": e.event, "agent_id": e.agent_id, "detail": e.detail, "created": e.created}
                for e in db.scalars(
                    select(MissionEvent)
                    .where(MissionEvent.mission_id == mission.id)
                    .order_by(MissionEvent.created)
                    .limit(200)
                )
            ]
            result["operations"] = (
                [
                    operation_view(db, o, user)
                    for o in db.scalars(select(Operation).where(Operation.mission_id == mission.id))
                ]
                if valid
                else []
            )
            result["evidence"] = json.loads(mission.context_json)["evidence"] if valid else []
            result["can_complete"] = (
                valid
                and all(s.status == "completed" for s in steps)
                and all(
                    o["status"] in {"succeeded", "rejected", "withdrawn"}
                    and o["work_status"] in {None, "done"}
                    for o in result["operations"]
                )
            )
        return result

    @router.get("/catalog")
    def catalog(p=Depends(principal), db: Session = Depends(session)):
        configured, identity = resolve_settings(db, settings, p.user.org_id)
        ready = (
            configured.provider in {"groq", "gemini"}
            and bool(configured.model)
            and bool(
                configured.groq_key if configured.provider == "groq" else configured.google_key
            )
        )
        return {
            "templates": TEMPLATES,
            "default_team": DEFAULT_TEAM.model_dump(),
            "ai_ready": ready,
            "model": identity,
            "tools": [
                "knowledge.search",
                "dataset.profile",
                "dataset.group_by",
                "github.open_issues",
                "internal.create_work_item",
                "github.create_issue",
                "slack.post_message",
            ],
            "execution_policy": "All writes require owner submission and a separate reviewer approval",
        }

    @router.put("/model")
    def configure_model(body: ModelInput, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        require_role(p, "admin")
        value = db.scalar(select(ModelProfile).where(ModelProfile.org_id == p.user.org_id))
        if not value:
            value = ModelProfile(
                org_id=p.user.org_id,
                provider=body.provider,
                model=body.model,
                secret_ciphertext=encrypt(settings, body.api_key),
            )
            db.add(value)
        else:
            value.provider, value.model, value.secret_ciphertext = (
                body.provider,
                body.model,
                encrypt(settings, body.api_key),
            )
            value.revision += 1
        audit(db, p.user, "model_profile.updated")
        db.commit()
        return {"provider": value.provider, "model": value.model, "revision": value.revision}

    @router.get("/teams")
    def teams(p=Depends(principal), db: Session = Depends(session)):
        rows = [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "definition": json.loads(t.definition),
                "revision": t.revision,
            }
            for t in db.scalars(select(AgentTeam).where(AgentTeam.org_id == p.user.org_id))
        ]
        return rows or [{"id": "default", **DEFAULT_TEAM.model_dump(), "revision": 1}]

    @router.post("/teams", status_code=201)
    def team_create(body: TeamInput, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        require_role(p, "admin")
        value = AgentTeam(
            org_id=p.user.org_id,
            name=body.name,
            description=body.description,
            definition=body.definition.model_dump_json(),
        )
        db.add(value)
        db.flush()
        audit(db, p.user, "agent_team.created", value.id)
        db.commit()
        return {"id": value.id}

    @router.put("/teams/{team_id}")
    def team_update(
        team_id: str, body: TeamInput, p=Depends(principal), db: Session = Depends(session)
    ):
        browser_only(p)
        require_role(p, "admin")
        value = db.scalar(
            select(AgentTeam).where(AgentTeam.id == team_id, AgentTeam.org_id == p.user.org_id)
        )
        if not value:
            raise HTTPException(404, "Agent team not found")
        value.name, value.description, value.definition = (
            body.name,
            body.description,
            body.definition.model_dump_json(),
        )
        value.revision += 1
        audit(db, p.user, "agent_team.updated", value.id)
        db.commit()
        return {"revision": value.revision}

    @router.get("/datasets")
    def datasets(p=Depends(principal), db: Session = Depends(session)):
        return [
            {
                "id": v.id,
                "title": v.title,
                "visibility": v.visibility,
                "department": v.department,
                "profile": json.loads(v.profile_json),
                "created": v.created,
            }
            for v in db.scalars(
                select(Dataset).where(Dataset.org_id == p.user.org_id, dataset_visible(p.user))
            )
        ]

    @router.post("/datasets", status_code=201)
    def dataset_create(
        file: UploadFile = File(...),
        title: str = Form(..., min_length=2, max_length=150),
        visibility: str = Form("organization"),
        p=Depends(principal),
        db: Session = Depends(session),
    ):
        browser_only(p)
        require_role(p, "admin")
        if visibility not in {"organization", "department", "admin"}:
            raise HTTPException(422, "Unknown visibility")
        content = file.file.read(2 * 1024 * 1024 + 1)
        try:
            columns, rows, computed = read_csv(content)
        except Exception:
            raise HTTPException(
                422,
                "Invalid CSV: up to 2 MB / 10,000 rows / 60 columns; use UTF-8 and consistent rows",
            ) from None
        value = Dataset(
            org_id=p.user.org_id,
            title=title,
            visibility=visibility,
            department=p.user.department,
            columns_json=json.dumps(columns),
            rows_json=json.dumps(rows, ensure_ascii=False),
            profile_json=json.dumps(computed, ensure_ascii=False),
            content_hash=hashlib.sha256(content).hexdigest(),
        )
        db.add(value)
        db.flush()
        audit(db, p.user, "dataset.uploaded", value.id)
        db.commit()
        return {"id": value.id, "profile": computed}

    @router.delete("/datasets/{dataset_id}")
    def dataset_delete(dataset_id: str, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        require_role(p, "admin")
        value = db.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id, Dataset.org_id == p.user.org_id, dataset_visible(p.user)
            )
        )
        if not value:
            raise HTTPException(404, "Dataset not found")
        db.delete(value)
        audit(db, p.user, "dataset.deleted", dataset_id)
        db.commit()
        return {"ok": True}

    @router.get("/connectors")
    def connectors(p=Depends(principal), db: Session = Depends(session)):
        return [
            {
                "id": v.id,
                "name": v.name,
                "kind": v.kind,
                "department": v.department,
                "config": json.loads(v.config_json),
                "enabled": v.enabled,
                "revision": v.revision,
            }
            for v in db.scalars(select(Connector).where(Connector.org_id == p.user.org_id))
            if v.department in {"General", p.user.department}
        ]

    @router.post("/connectors", status_code=201)
    def connector_create(
        body: ConnectorInput, p=Depends(principal), db: Session = Depends(session)
    ):
        browser_only(p)
        require_role(p, "admin")
        if body.department not in {"General", p.user.department}:
            raise HTTPException(403, "Choose your department or General")
        try:
            validate_config(body.kind, body.config)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        value = Connector(
            org_id=p.user.org_id,
            name=body.name,
            kind=body.kind,
            department=body.department,
            config_json=json.dumps(body.config),
            secret_ciphertext=encrypt(settings, body.token),
        )
        db.add(value)
        db.flush()
        audit(db, p.user, "connector.created", value.id)
        db.commit()
        return {"id": value.id}

    @router.post("/connectors/{connector_id}/toggle")
    def connector_toggle(connector_id: str, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        require_role(p, "admin")
        value = db.get(Connector, connector_id)
        if (
            not value
            or value.org_id != p.user.org_id
            or value.department not in {"General", p.user.department}
        ):
            raise HTTPException(404, "Connector not found")
        value.enabled = not value.enabled
        value.revision += 1
        audit(db, p.user, "connector.toggled", value.id)
        db.commit()
        return {"enabled": value.enabled}

    @router.post("/connectors/{connector_id}/test")
    def connector_test(connector_id: str, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        require_role(p, "admin")
        value = db.get(Connector, connector_id)
        if not value or not allowed(value, p.user):
            raise HTTPException(404, "Connector not found")
        try:
            context = read_context(settings, value)
        except ConnectorError:
            raise HTTPException(
                502, "Connector read failed; verify credentials and permissions"
            ) from None
        return {
            "status": "read_verified" if value.kind == "github" else "configured_write_destination",
            "context": context,
        }

    @router.get("/missions")
    def missions(p=Depends(principal), db: Session = Depends(session)):
        return [
            mission_view(db, m, p.user)
            for m in db.scalars(
                select(Mission)
                .where(Mission.org_id == p.user.org_id, Mission.user_id == p.user.id)
                .order_by(Mission.created.desc())
                .limit(100)
            )
        ]

    @router.post("/missions", status_code=201)
    def mission_create(body: MissionInput, p=Depends(principal), db: Session = Depends(session)):
        try:
            value = create_mission(db, p.user, body, settings)
            db.commit()
        except (MissionBlocked, ConnectorError, ValueError) as error:
            db.rollback()
            raise HTTPException(422, str(error)) from None
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Request key exists; retry the identical request") from None
        return mission_view(db, value, p.user)

    @router.get("/missions/{mission_id}")
    def mission_detail(mission_id: str, p=Depends(principal), db: Session = Depends(session)):
        return mission_view(db, owner(db, mission_id, p.user), p.user, True)

    @router.post("/missions/{mission_id}/run")
    def mission_run(mission_id: str, p=Depends(principal), db: Session = Depends(session)):
        value = owner(db, mission_id, p.user)
        if not accessible(db, value, p.user):
            raise HTTPException(409, "Source access changed; create a new mission")
        db.rollback()
        process_mission(factory, settings, mission_id)
        db.expire_all()
        return mission_view(db, owner(db, mission_id, p.user), p.user, True)

    @router.post("/missions/{mission_id}/retry")
    def mission_retry(mission_id: str, p=Depends(principal), db: Session = Depends(session)):
        value = owner(db, mission_id, p.user)
        if value.status != "failed" or not accessible(db, value, p.user):
            raise HTTPException(409, "Only failed missions with valid sources can resume")
        value.status = "queued"
        value.error_code = ""
        value.updated = time.time()
        event(db, value, "mission.retry_requested")
        db.commit()
        return {"status": "queued"}

    @router.post("/missions/{mission_id}/cancel")
    def mission_cancel(mission_id: str, p=Depends(principal), db: Session = Depends(session)):
        value = owner(db, mission_id, p.user)
        if db.scalar(
            select(Operation.id).where(
                Operation.mission_id == mission_id,
                Operation.status.in_(["approved", "executing", "succeeded", "uncertain"]),
            )
        ):
            raise HTTPException(
                409, "Dispatched actions cannot be cancelled as if they had no effect"
            )
        value.status = "cancelled"
        value.lease_until = 0
        db.execute(
            update(Operation)
            .where(Operation.mission_id == mission_id, Operation.status.in_(["draft", "pending"]))
            .values(status="withdrawn")
        )
        event(db, value, "mission.cancelled")
        db.commit()
        return {"status": "cancelled"}

    @router.post("/missions/{mission_id}/submit-actions")
    def submit_actions(
        mission_id: str, body: SubmitInput, p=Depends(principal), db: Session = Depends(session)
    ):
        value = owner(db, mission_id, p.user)
        if value.status not in {"ready", "review_required", "awaiting_approval"} or not accessible(
            db, value, p.user
        ):
            raise HTTPException(409, "Mission is not ready or sources changed")
        if not body.acknowledge_review:
            raise HTTPException(
                422, "Review and acknowledge sharing exact arguments with authorized approvers"
            )
        rows = list(
            db.scalars(
                select(Operation).where(
                    Operation.mission_id == mission_id, Operation.id.in_(body.operation_ids)
                )
            )
        )
        if len(rows) != len(set(body.operation_ids)) or any(r.status != "draft" for r in rows):
            raise HTTPException(409, "Select unsubmitted drafts from this mission")
        for operation in rows:
            operation.status = "pending"
        value.status = "awaiting_approval"
        event(db, value, "operations.submitted")
        audit(db, p.user, "mission.actions_shared", mission_id)
        db.commit()
        return {"submitted": len(rows)}

    @router.post("/missions/{mission_id}/refine")
    def refine(
        mission_id: str, body: Refinement, p=Depends(principal), db: Session = Depends(session)
    ):
        value = owner(db, mission_id, p.user)
        if (
            value.status not in {"ready", "review_required"}
            or value.iteration >= 2
            or not accessible(db, value, p.user)
        ):
            raise HTTPException(
                409, "Only ready missions with valid sources can be refined, up to two rounds"
            )
        if db.scalar(
            select(Operation.id).where(
                Operation.mission_id == mission_id,
                Operation.status.in_(
                    ["pending", "approved", "executing", "succeeded", "uncertain"]
                ),
            )
        ):
            raise HTTPException(409, "Withdraw shared actions before revising the plan")
        db.execute(
            update(Operation)
            .where(Operation.mission_id == mission_id, Operation.status == "draft")
            .values(status="withdrawn")
        )
        definition = json.loads(value.team_snapshot)
        reset = {
            a["id"] for a in definition["agents"] if a["role"] in {"planner", "reviewer", "writer"}
        }
        for _ in definition["agents"]:
            reset |= {a["id"] for a in definition["agents"] if set(a["depends_on"]) & reset}
        db.execute(
            update(AgentStep)
            .where(AgentStep.mission_id == mission_id, AgentStep.agent_id.in_(reset))
            .values(status="queued", attempts=0, output_json="{}", started=0, completed=0)
        )
        context = json.loads(value.context_json)
        context.setdefault("human_feedback", []).append(body.feedback)
        value.context_json = json.dumps(context)
        value.iteration += 1
        value.status = "queued"
        value.updated = time.time()
        event(
            db,
            value,
            "mission.refinement_requested",
            detail="Human feedback recorded; upstream evidence checkpoints retained",
        )
        db.commit()
        return {"status": "queued", "iteration": value.iteration}

    @router.get("/missions/{mission_id}/artifacts")
    def artifacts(mission_id: str, p=Depends(principal), db: Session = Depends(session)):
        value = owner(db, mission_id, p.user)
        if not accessible(db, value, p.user):
            raise HTTPException(409, "Source access changed")
        return [
            {
                "id": a.id,
                "agent_id": a.agent_id,
                "iteration": a.iteration,
                "content_hash": a.content_hash,
                "output": json.loads(a.output_json),
                "created": a.created,
            }
            for a in db.scalars(
                select(AgentArtifact)
                .where(AgentArtifact.mission_id == mission_id)
                .order_by(AgentArtifact.created)
            )
        ]

    @router.post("/missions/{mission_id}/complete")
    def mission_complete(
        mission_id: str, body: MissionOutcome, p=Depends(principal), db: Session = Depends(session)
    ):
        value = owner(db, mission_id, p.user)
        detail = mission_view(db, value, p.user, True)
        if not detail["can_complete"] or value.status in {
            "queued",
            "running",
            "failed",
            "cancelled",
        }:
            raise HTTPException(
                409,
                "Resolve or withdraw proposals and finish all internal work before closing the objective",
            )
        value.status, value.outcome, value.finished = "completed", body.outcome, time.time()
        event(db, value, "mission.completed", detail="Owner recorded an operational outcome")
        audit(db, p.user, "mission.completed", value.id)
        db.commit()
        return {"status": "completed"}

    @router.post("/operations/{operation_id}/withdraw")
    def operation_withdraw(operation_id: str, p=Depends(principal), db: Session = Depends(session)):
        value = db.get(Operation, operation_id)
        if not value or value.org_id != p.user.org_id or value.requester_id != p.user.id:
            raise HTTPException(404, "Operation not found")
        if not db.execute(
            update(Operation)
            .where(Operation.id == operation_id, Operation.status.in_(["draft", "pending"]))
            .values(status="withdrawn")
        ).rowcount:
            raise HTTPException(409, "A dispatched or decided action cannot be withdrawn")
        event(db, db.get(Mission, value.mission_id), "operation.withdrawn", detail=value.id)
        db.commit()
        return {"status": "withdrawn"}

    @router.get("/missions/{mission_id}/export")
    def export(mission_id: str, p=Depends(principal), db: Session = Depends(session)):
        value = owner(db, mission_id, p.user)
        detail = mission_view(db, value, p.user, True)
        if not detail["access_valid"]:
            raise HTTPException(409, "Sources changed; export blocked")
        lines = [
            "# " + value.title,
            "",
            value.objective,
            "",
            f"Mode: {value.mode}. Status: {value.status}.",
            "",
        ]
        if value.outcome:
            lines.extend(["## Owner-recorded outcome", value.outcome, ""])
        for agent in detail["agents"]:
            if agent["output"]:
                lines.extend(["## " + agent["name"], "", agent["output"]["summary"], ""])
                lines.extend(
                    f"- ({f['category']}) {f['statement']} Sources: {', '.join(f['evidence_ids'])}"
                    for f in agent["output"]["findings"]
                )
                lines.extend("- Risk: " + r for r in agent["output"]["risks"])
        lines.extend(["", "## Action receipts", ""])
        lines.extend(
            f"- {o['title']}: {o['status']}; {json.dumps(o['result'])}"
            for o in detail["operations"]
        )
        return Response(
            "\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="aivora-{mission_id}.md"'},
        )

    @router.get("/approvals")
    def approvals(p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        return [
            operation_view(db, o, p.user)
            for o in db.scalars(
                select(Operation)
                .where(Operation.org_id == p.user.org_id, Operation.status != "draft")
                .order_by(Operation.created.desc())
                .limit(200)
            )
            if (o.requester_id == p.user.id or review_allowed(o, p.user)) and valid_requester(db, o)
        ]

    @router.post("/operations/{operation_id}/decision")
    def decision(
        operation_id: str, body: DecisionInput, p=Depends(principal), db: Session = Depends(session)
    ):
        browser_only(p)
        value = db.get(Operation, operation_id)
        if not value or value.org_id != p.user.org_id:
            raise HTTPException(404, "Operation not found")
        if not review_allowed(value, p.user):
            raise HTTPException(403, "A separate authorized reviewer must decide")
        if (
            value.status != "pending"
            or value.expires <= time.time()
            or not valid_requester(db, value)
        ):
            raise HTTPException(409, "Operation no longer eligible")
        claimed = db.execute(
            update(Operation)
            .where(Operation.id == operation_id, Operation.status == "pending")
            .values(
                status="approved" if body.decision == "approve" else "rejected",
                reviewer_id=p.user.id,
                reviewer_note=body.note,
            )
        ).rowcount
        if not claimed:
            raise HTTPException(409, "Another reviewer already decided")
        audit(db, p.user, "operation." + body.decision, value.id)
        event(db, db.get(Mission, value.mission_id), "operation." + body.decision, detail=value.id)
        db.commit()
        if body.decision == "approve":
            execute_operation(factory, settings, operation_id)
        db.expire_all()
        return operation_view(db, db.get(Operation, operation_id), p.user)

    @router.get("/work-items")
    def work_items(p=Depends(principal), db: Session = Depends(session)):
        return [
            {
                "id": w.id,
                "title": w.title,
                "description": w.description,
                "department": w.department,
                "owner_id": w.owner_id,
                "status": w.status,
                "outcome": w.outcome,
                "updated": w.updated,
                "mission_id": db.get(Operation, w.operation_id).mission_id,
                "can_update": w.owner_id == p.user.id
                or p.user.role == "admin"
                or p.user.role == "reviewer"
                and w.department in {"General", p.user.department},
            }
            for w in db.scalars(select(WorkItem).where(WorkItem.org_id == p.user.org_id))
            if w.owner_id == p.user.id
            or w.department in {"General", p.user.department}
            or p.user.role == "admin"
        ]

    @router.put("/work-items/{item_id}")
    def work_update(
        item_id: str, body: WorkUpdate, p=Depends(principal), db: Session = Depends(session)
    ):
        browser_only(p)
        value = db.get(WorkItem, item_id)
        if not value or value.org_id != p.user.org_id:
            raise HTTPException(404, "Work item not found")
        if not (
            value.owner_id == p.user.id
            or p.user.role == "admin"
            or p.user.role == "reviewer"
            and value.department in {"General", p.user.department}
        ):
            raise HTTPException(403, "You cannot update this work item")
        if body.status == "done" and len(body.outcome) < 10:
            raise HTTPException(422, "Record a concrete outcome before marking done")
        value.status, value.outcome, value.updated = body.status, body.outcome, time.time()
        audit(db, p.user, "work_item.updated", value.id)
        db.commit()
        return {"ok": True}

    @router.get("/schedules")
    def schedules(p=Depends(principal), db: Session = Depends(session)):
        return [
            {
                "id": s.id,
                "name": s.name,
                "interval_hours": s.interval_hours,
                "next_run": s.next_run,
                "enabled": s.enabled,
            }
            for s in db.scalars(
                select(MissionSchedule).where(
                    MissionSchedule.org_id == p.user.org_id, MissionSchedule.user_id == p.user.id
                )
            )
        ]

    @router.post("/schedules", status_code=201)
    def schedule_create(body: ScheduleInput, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        try:
            create_mission(db, p.user, body.template, settings)
            db.rollback()
        except Exception:
            db.rollback()
            raise HTTPException(422, "Mission template could not be validated") from None
        value = MissionSchedule(
            org_id=p.user.org_id,
            user_id=p.user.id,
            name=body.name,
            mission_template_json=body.template.model_dump_json(),
            interval_hours=body.interval_hours,
            next_run=time.time(),
        )
        db.add(value)
        db.flush()
        audit(db, p.user, "mission_schedule.created", value.id)
        db.commit()
        return {"id": value.id}

    @router.post("/schedules/{schedule_id}/toggle")
    def schedule_toggle(schedule_id: str, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        value = db.get(MissionSchedule, schedule_id)
        if not value or value.user_id != p.user.id or value.org_id != p.user.org_id:
            raise HTTPException(404, "Schedule not found")
        value.enabled = not value.enabled
        db.commit()
        return {"enabled": value.enabled}

    @router.get("/hooks")
    def hooks(p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        return [
            {
                "id": v.id,
                "name": v.name,
                "enabled": v.enabled,
                "url": settings.origin + "/api/ops/hooks/" + v.id + "/events",
            }
            for v in db.scalars(
                select(IncomingHook).where(
                    IncomingHook.org_id == p.user.org_id, IncomingHook.user_id == p.user.id
                )
            )
        ]

    @router.post("/hooks", status_code=201)
    def hook_create(body: HookInput, p=Depends(principal), db: Session = Depends(session)):
        browser_only(p)
        try:
            create_mission(db, p.user, body.template, settings)
            db.rollback()
        except Exception:
            db.rollback()
            raise HTTPException(422, "Mission template could not be validated") from None
        secret = secrets.token_urlsafe(32)
        value = IncomingHook(
            org_id=p.user.org_id,
            user_id=p.user.id,
            name=body.name,
            template_json=body.template.model_dump_json(),
            secret_ciphertext=encrypt(settings, secret),
        )
        db.add(value)
        db.flush()
        audit(db, p.user, "mission_hook.created", value.id)
        db.commit()
        return {
            "id": value.id,
            "secret": secret,
            "url": settings.origin + "/api/ops/hooks/" + value.id + "/events",
        }

    @router.post("/hooks/{hook_id}/events", status_code=202)
    async def hook_event(hook_id: str, request: Request, db: Session = Depends(session)):
        hook = db.get(IncomingHook, hook_id)
        if not hook or not hook.enabled:
            raise HTTPException(404, "Hook not found")
        raw = await request.body()
        if len(raw) > 16000:
            raise HTTPException(413, "Event body too large")
        timestamp = request.headers.get("x-aivora-timestamp", "")
        if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(401, "Expired or invalid timestamp")
        expected = hmac.new(
            decrypt(settings, hook.secret_ciphertext).encode(),
            timestamp.encode() + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(request.headers.get("x-aivora-signature", ""), expected):
            raise HTTPException(401, "Invalid event signature")
        try:
            payload = HookPayload.model_validate_json(raw)
        except ValueError:
            raise HTTPException(422, "Invalid event payload") from None
        previous = db.scalar(
            select(HookEvent).where(
                HookEvent.hook_id == hook_id, HookEvent.external_id == payload.event_id
            )
        )
        hashed = hashlib.sha256(raw).hexdigest()
        if previous:
            if previous.payload_hash != hashed:
                raise HTTPException(409, "Event ID reused for another payload")
            return {"mission_id": previous.mission_id, "duplicate": True}
        user = db.get(User, hook.user_id)
        if not user or not user.active:
            raise HTTPException(403, "Hook owner inactive")
        data = json.loads(hook.template_json)
        data["request_key"] = (
            "hook:" + hook.id + ":" + hashlib.sha256(payload.event_id.encode()).hexdigest()[:32]
        )
        data["objective"] = (
            data["objective"][:2700]
            + "\nExternal event context (untrusted data):\n"
            + payload.context
        )
        try:
            value = create_mission(db, user, MissionInput.model_validate(data), settings)
        except Exception:
            db.rollback()
            raise HTTPException(
                422, "Cannot create mission under owner's current permissions"
            ) from None
        db.add(
            HookEvent(
                hook_id=hook_id,
                external_id=payload.event_id,
                payload_hash=hashed,
                mission_id=value.id,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Concurrent event; retry the same event ID") from None
        return {"mission_id": value.id, "duplicate": False}

    app.include_router(router)
