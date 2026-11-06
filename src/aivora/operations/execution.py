import hashlib
import json
import time

from sqlalchemy import select, update

from ..db import User
from .connectors import ConnectorError, UncertainDelivery, allowed, execute_external
from .models import Connector, Mission, Operation, WorkItem
from .runtime import context_valid, event


def review_allowed(operation, user):
    return (
        operation.org_id == user.org_id
        and operation.requester_id != user.id
        and (
            user.role == "admin"
            or user.role == "reviewer"
            and operation.department in {"General", user.department}
        )
    )


def valid_requester(db, operation):
    user = db.get(User, operation.requester_id)
    mission = db.get(Mission, operation.mission_id)
    if not user or not user.active or not context_valid(db, user, json.loads(mission.context_json)):
        return False
    canonical = json.dumps(
        json.loads(operation.arguments_json), sort_keys=True, separators=(",", ":")
    )
    if hashlib.sha256(canonical.encode()).hexdigest() != operation.arguments_hash:
        return False
    if operation.connector_id:
        connector = db.get(Connector, operation.connector_id)
        if (
            not connector
            or not allowed(connector, user)
            or connector.revision != operation.connector_revision
        ):
            return False
    return True


def execute_operation(factory, settings, operation_id):
    with factory.begin() as db:
        operation = db.get(Operation, operation_id)
        if not operation or operation.status != "approved":
            return False
        reviewer = db.get(User, operation.reviewer_id)
        if (
            not reviewer
            or not reviewer.active
            or not review_allowed(operation, reviewer)
            or not valid_requester(db, operation)
            or operation.expires <= time.time()
        ):
            operation.status = "blocked"
            event(
                db, db.get(Mission, operation.mission_id), "operation.blocked", detail=operation.id
            )
            return False
        claimed = db.execute(
            update(Operation)
            .where(Operation.id == operation_id, Operation.status == "approved")
            .values(status="executing", executing_since=time.time())
        ).rowcount
        if not claimed:
            return False
        arguments = json.loads(operation.arguments_json)
        if operation.kind == "work_item":
            item = WorkItem(
                org_id=operation.org_id,
                operation_id=operation.id,
                title=arguments["title"],
                description=arguments["description"],
                department=operation.department,
                owner_id=operation.requester_id,
            )
            db.add(item)
            db.flush()
            operation.status = "succeeded"
            operation.result_json = json.dumps(
                {"work_item_id": item.id, "receipt": "internal_database_transaction"}
            )
            event(
                db,
                db.get(Mission, operation.mission_id),
                "operation.succeeded",
                detail=operation.id,
            )
            return True
        connector = db.get(Connector, operation.connector_id)
        # A durable executing marker precedes any external write. A crash is reconciled, never blindly retried.
    status = "succeeded"
    try:
        result = execute_external(settings, connector, operation_id, arguments)
    except UncertainDelivery:
        status, result = (
            "uncertain",
            {
                "message": "External delivery is unknown. Do not retry; reconcile in the target system."
            },
        )
    except ConnectorError:
        status, result = "failed", {"message": "The target rejected the approved action"}
    except Exception:
        status, result = "uncertain", {"message": "Execution ended without a verified receipt"}
    with factory.begin() as db:
        operation = db.get(Operation, operation_id)
        if operation.status == "executing":
            operation.status, operation.result_json = status, json.dumps(result)
            event(
                db,
                db.get(Mission, operation.mission_id),
                "operation." + status,
                detail=operation.id,
            )
    return status == "succeeded"


def run_approved(factory, settings):
    with factory.begin() as db:
        # If a worker died after dispatch, it is unsafe to infer that the external effect did not happen.
        db.execute(
            update(Operation)
            .where(Operation.status == "executing", Operation.executing_since < time.time() - 120)
            .values(
                status="uncertain",
                result_json=json.dumps(
                    {"message": "Worker interrupted after dispatch; reconcile before retrying"}
                ),
            )
        )
        ids = list(db.scalars(select(Operation.id).where(Operation.status == "approved").limit(10)))
    return sum(execute_operation(factory, settings, operation_id) for operation_id in ids)
