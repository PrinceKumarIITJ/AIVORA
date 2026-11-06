import hashlib
import hmac
import json
import time

from conftest import member, register, upload
from fastapi.testclient import TestClient

from aivora.operations import agents
from aivora.operations.contracts import DEFAULT_TEAM
from aivora.operations.models import Connector
from aivora.operations.scheduler import run_mission_schedules


def mission(client, mode="evidence", **kwargs):
    body = {
        "title": "Cross-department improvement",
        "objective": "Analyze support bottlenecks and the available policy evidence. Create a trackable cross-department improvement plan.",
        "team_id": "default",
        "mode": mode,
        "request_key": "operations-test-mission-1",
        **kwargs,
    }
    response = client.post("/api/ops/missions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def dataset(owner, visibility="organization"):
    response = owner.post(
        "/api/ops/datasets",
        data={"title": "Support operations", "visibility": visibility},
        files={
            "file": (
                "support.csv",
                b"department,status,hours\nSupport,pending,12\nSupport,pending,8\nOperations,done,2\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def run(owner, value):
    response = owner.post("/api/ops/missions/" + value["id"] + "/run")
    assert response.status_code == 200, response.text
    return response.json()


def test_six_agent_evidence_mission_analytics_and_export(owner):
    upload(
        owner,
        "Support procedures require an owner, a documented cause and evidence before changing a process.",
    )
    data = dataset(owner)
    assert data["profile"]["columns"]["hours"]["total"] == "22"
    value = mission(owner, dataset_ids=[data["id"]], group_by="department", metric="hours")
    result = run(owner, value)
    assert result["status"] == "review_required", result
    assert result["completed_agents"] == 6
    analyst = next(a for a in result["agents"] if a["role"] == "analyst")
    assert "22" in str(analyst["output"])
    assert len(result["operations"]) == 1 and result["operations"][0]["status"] == "draft"
    assert owner.get("/api/ops/missions/" + value["id"] + "/export").status_code == 200
    assert "agent.started" in str(result["events"])
    assert result["model_calls"] == 0


def test_mission_privacy_and_source_revocation(app, owner):
    data = dataset(owner)
    value = mission(owner, dataset_ids=[data["id"]])
    run(owner, value)
    employee = member(app, owner, "employee@acme.test")
    other = register(TestClient(app), "other@beta.test", "Beta Academy")
    assert employee.get("/api/ops/missions").json() == []
    assert employee.get("/api/ops/missions/" + value["id"]).status_code == 404
    assert other.get("/api/ops/missions/" + value["id"]).status_code == 404
    assert owner.delete("/api/ops/datasets/" + data["id"]).status_code == 200
    hidden = owner.get("/api/ops/missions/" + value["id"]).json()
    assert (
        not hidden["access_valid"]
        and not hidden["operations"]
        and all(a["output"] is None for a in hidden["agents"])
    )
    assert owner.get("/api/ops/missions/" + value["id"] + "/export").status_code == 409


def test_drafts_are_not_executed_and_separate_reviewer_required(app, owner):
    value = mission(owner)
    result = run(owner, value)
    operation = result["operations"][0]
    reviewer = member(app, owner, "reviewer@acme.test", "reviewer")
    assert reviewer.get("/api/ops/approvals").json() == []
    assert (
        owner.post(
            "/api/ops/missions/" + value["id"] + "/submit-actions",
            json={"operation_ids": [operation["id"]]},
        ).status_code
        == 422
    )
    assert (
        owner.post(
            "/api/ops/missions/" + value["id"] + "/submit-actions",
            json={"operation_ids": [operation["id"]], "acknowledge_review": True},
        ).status_code
        == 200
    )
    assert (
        owner.post(
            "/api/ops/operations/" + operation["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 403
    )
    approved = reviewer.post(
        "/api/ops/operations/" + operation["id"] + "/decision", json={"decision": "approve"}
    )
    assert approved.status_code == 200 and approved.json()["status"] == "succeeded", approved.text
    assert (
        reviewer.post(
            "/api/ops/operations/" + operation["id"] + "/decision", json={"decision": "approve"}
        ).status_code
        == 409
    )
    work = owner.get("/api/ops/work-items").json()
    assert len(work) == 1
    assert (
        owner.put("/api/ops/work-items/" + work[0]["id"], json={"status": "done"}).status_code
        == 422
    )
    assert (
        owner.put(
            "/api/ops/work-items/" + work[0]["id"],
            json={
                "status": "done",
                "outcome": "Reviewed evidence and updated the agreed support ownership process.",
            },
        ).status_code
        == 200
    )


def test_invalid_team_dependencies_rejected(owner):
    body = DEFAULT_TEAM.model_dump()
    body["definition"]["agents"][0]["depends_on"] = ["report"]
    assert owner.post("/api/ops/teams", json=body).status_code == 422
    body = DEFAULT_TEAM.model_dump()
    body["definition"]["agents"][-1]["depends_on"] = ["coordinate"]
    assert owner.post("/api/ops/teams", json=body).status_code == 422


def test_identity_and_dataset_acl_cannot_be_overridden(app, owner):
    data = dataset(owner, "admin")
    employee = member(app, owner, "employee@acme.test")
    assert employee.get("/api/ops/datasets").json() == []
    body = {
        "title": "Forbidden analysis",
        "objective": "Analyze the restricted dataset and report its contents.",
        "team_id": "default",
        "mode": "evidence",
        "request_key": "forbidden-dataset-key",
        "dataset_ids": [data["id"]],
    }
    assert employee.post("/api/ops/missions", json=body).status_code == 422
    body["org_id"] = "fake"
    assert employee.post("/api/ops/missions", json=body).status_code == 422


def test_ai_mode_is_not_silently_simulated(owner):
    response = owner.post(
        "/api/ops/missions",
        json={
            "title": "Actual AI mission",
            "objective": "Investigate operational issues with the specialist team.",
            "team_id": "default",
            "mode": "ai",
            "request_key": "ai-not-configured",
        },
    )
    assert response.status_code == 422 and "provider_not_configured" in response.text


def test_mission_idempotency_includes_inputs(owner):
    value = mission(owner)
    assert mission(owner)["id"] == value["id"]
    response = owner.post(
        "/api/ops/missions",
        json={
            "title": value["title"],
            "objective": value["objective"],
            "team_id": "default",
            "mode": "evidence",
            "request_key": "operations-test-mission-1",
            "max_tokens": 15000,
        },
    )
    assert response.status_code == 422 and "request_key_conflict" in response.text


def test_signed_webhook_replay_and_tampering(owner):
    template = {
        "title": "Triggered operations review",
        "objective": "Review the operational event and prepare a documented response plan.",
        "team_id": "default",
        "mode": "evidence",
        "request_key": "template-key-hook-1",
    }
    response = owner.post("/api/ops/hooks", json={"name": "Operations event", "template": template})
    assert response.status_code == 201, response.text
    hook = response.json()
    raw = json.dumps(
        {
            "event_id": "event-001",
            "context": "Support queue has an escalation requiring investigation.",
        }
    ).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        hook["secret"].encode(), timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    headers = {
        "x-aivora-timestamp": timestamp,
        "x-aivora-signature": signature,
        "content-type": "application/json",
    }
    path = "/api/ops/hooks/" + hook["id"] + "/events"
    first = owner.post(path, content=raw, headers=headers)
    assert first.status_code == 202, first.text
    replay = owner.post(path, content=raw, headers=headers)
    assert replay.json()["duplicate"] and replay.json()["mission_id"] == first.json()["mission_id"]
    assert owner.post(path, content=raw + b" ", headers=headers).status_code == 401
    headers["x-aivora-timestamp"] = "1"
    assert owner.post(path, content=raw, headers=headers).status_code == 401


def test_scheduled_mission_runs_under_current_owner_permissions(app, owner):
    template = {
        "title": "Daily operations review",
        "objective": "Review the operational evidence and prepare a daily action brief.",
        "team_id": "default",
        "mode": "evidence",
        "request_key": "scheduled-template-key",
    }
    result = owner.post(
        "/api/ops/schedules",
        json={"name": "Daily operations", "interval_hours": 24, "template": template},
    )
    assert result.status_code == 201, result.text
    assert run_mission_schedules(app.state.factory, app.state.settings) == 1
    assert run_mission_schedules(app.state.factory, app.state.settings) == 0
    assert len(owner.get("/api/ops/missions").json()) == 1


def test_ai_agents_are_distinct_parallel_and_checkpointed(app, owner, monkeypatch):
    assert (
        owner.put(
            "/api/ops/model",
            json={
                "provider": "groq",
                "model": "test-model",
                "api_key": "fake-provider-secret-for-test",
            },
        ).status_code
        == 200
    )
    calls = []

    def fake(settings, agent, payload):
        calls.append(agent.role)
        if agent.role in {"researcher", "analyst"}:
            time.sleep(0.05)
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    value = mission(owner, "ai")
    result = run(owner, value)
    assert result["status"] == "ready", result
    assert len(calls) == 6 and set(calls) == {
        "coordinator",
        "researcher",
        "analyst",
        "planner",
        "reviewer",
        "writer",
    }
    assert result["model_calls"] == 6 and result["input_tokens"] == 120
    run(owner, value)
    assert len(calls) == 6


def test_failed_agent_resume_reuses_completed_checkpoints(app, owner, monkeypatch):
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "test-model",
            "api_key": "fake-provider-secret-for-test",
        },
    )
    calls = []
    fail = [True]

    def fake(settings, agent, payload):
        calls.append(agent.role)
        if agent.role == "planner" and fail[0]:
            raise agents.InvalidOutput("Test interruption")
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    value = mission(owner, "ai")
    result = run(owner, value)
    assert result["status"] == "failed" and result["error_code"] == "invalid_agent_output"
    fail[0] = False
    assert owner.post("/api/ops/missions/" + value["id"] + "/retry").status_code == 200
    result = run(owner, value)
    assert result["status"] == "ready", result
    assert (
        calls.count("coordinator") == 1
        and calls.count("researcher") == 1
        and calls.count("planner") == 2
    )


def test_connector_secret_is_encrypted_and_never_returned(app, owner):
    token = "fake-connector-secret-for-contract-test"
    response = owner.post(
        "/api/ops/connectors",
        json={
            "name": "Issue tracker",
            "kind": "github",
            "config": {"repository": "sample/operations"},
            "token": token,
        },
    )
    assert response.status_code == 201, response.text
    assert token not in owner.get("/api/ops/connectors").text
    with app.state.factory() as db:
        value = db.get(Connector, response.json()["id"])
        assert token not in value.secret_ciphertext
    assert (
        owner.post(
            "/api/ops/connectors",
            json={
                "name": "Bad target",
                "kind": "github",
                "config": {"repository": "https://localhost/secrets"},
                "token": token,
            },
        ).status_code
        == 422
    )
