import time
from concurrent.futures import ThreadPoolExecutor

from conftest import member, register
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from aivora.api import create_app
from aivora.db import Action, Ticket


def propose(client, key="test-proposal-0001", title="Need access"):
    workflow = client.get("/api/workflows").json()[0]
    return client.post(
        "/api/actions",
        json={
            "workflow_id": workflow["id"],
            "title": title,
            "description": "Please enable the requested tool for my work.",
            "idempotency_key": key,
        },
    )


def test_approved_action_and_replay_produce_one_ticket(app, owner):
    employee = member(app, owner, "employee@acme.test")
    action = propose(employee).json()
    assert action["status"] == "pending"
    assert (
        employee.post(
            "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 403
    )
    decision = owner.post(
        "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "executed" and decision.json()["ticket_id"]
    replay = owner.post("/api/actions/" + action["id"] + "/decision", json={"decision": "approve"})
    assert replay.json()["ticket_id"] == decision.json()["ticket_id"]
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Ticket)) == 1
    assert owner.post("/api/actions/" + action["id"] + "/resolve").status_code == 200
    assert employee.get("/api/actions").json()[0]["ticket_status"] == "resolved"


def test_admin_cannot_self_approve(owner):
    action = propose(owner).json()
    assert (
        owner.post(
            "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 403
    )


def test_request_idempotency_conflict(owner):
    first = propose(owner).json()
    assert propose(owner).json()["id"] == first["id"]
    assert propose(owner, title="Different operation").status_code == 409


def test_reviewer_department_and_request_visibility(app, owner):
    employee = member(app, owner, "employee@acme.test")
    reviewer = member(app, owner, "reviewer@acme.test", "reviewer", "Sales")
    workflow = next(w for w in employee.get("/api/workflows").json() if w["department"] == "IT")
    action = employee.post(
        "/api/actions",
        json={
            "workflow_id": workflow["id"],
            "title": "Access tool",
            "description": "Software access for project work",
            "idempotency_key": "department-test-1",
        },
    ).json()
    assert reviewer.get("/api/actions").json() == []
    assert (
        reviewer.post(
            "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 403
    )
    outsider = member(app, owner, "other@acme.test")
    assert outsider.get("/api/actions").json() == []


def test_rejected_action_never_executes(app, owner):
    employee = member(app, owner, "employee@acme.test")
    action = propose(employee).json()
    assert (
        owner.post(
            "/api/actions/" + action["id"] + "/decision",
            json={"decision": "reject", "reason": "Insufficient context"},
        ).json()["status"]
        == "rejected"
    )
    assert (
        owner.post(
            "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 409
    )
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Ticket)) == 0


def test_expired_and_deactivated_requester_cannot_execute(app, owner):
    employee = member(app, owner, "employee@acme.test")
    action = propose(employee).json()
    with app.state.factory.begin() as db:
        db.get(Action, action["id"]).expires = time.time() - 1
    assert (
        owner.post(
            "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 409
    )


def test_pending_approval_survives_application_restart(app, owner):
    employee = member(app, owner, "employee@acme.test")
    action = propose(employee).json()
    restarted = TestClient(create_app(app.state.settings))
    restarted.cookies.update(owner.cookies)
    restarted.headers.update(owner.headers)
    result = restarted.post(
        "/api/actions/" + action["id"] + "/decision", json={"decision": "approve"}
    )
    assert result.status_code == 200 and result.json()["ticket_id"]


def test_simultaneous_reviewers_create_one_ticket(app, owner):
    employee = member(app, owner, "employee@acme.test")
    reviewer = member(app, owner, "reviewer@acme.test", "admin")
    action = propose(employee).json()
    path = "/api/actions/" + action["id"] + "/decision"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(c.post, path, json={"decision": "approve"}) for c in (owner, reviewer)
        ]
        responses = [f.result() for f in futures]
    assert all(r.status_code in {200, 409} for r in responses)
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Ticket)) == 1


def test_cross_tenant_workflow_rejected(app, owner):
    foreign = register(TestClient(app), "owner@beta.test", "Beta School")
    workflow = owner.get("/api/workflows").json()[0]
    result = foreign.post(
        "/api/actions",
        json={
            "workflow_id": workflow["id"],
            "title": "Foreign request",
            "description": "Not allowed across organizations",
            "idempotency_key": "foreign-request-1",
        },
    )
    assert result.status_code == 404
