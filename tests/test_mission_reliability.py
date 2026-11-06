import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import member
from sqlalchemy import func, select
from test_operations_platform import mission, run

from aivora.operations import agents
from aivora.operations.contracts import DEFAULT_TEAM, ActionDraft, AgentOutput, Finding
from aivora.operations.models import Mission, Operation, WorkItem
from aivora.operations.runtime import process_mission


def test_mission_closure_requires_finished_work_and_recorded_outcome(app, owner):
    reviewer = member(app, owner, "reviewer@acme.test", "reviewer")
    value = mission(owner)
    detail = run(owner, value)
    operation = detail["operations"][0]
    close = "/api/ops/missions/" + value["id"] + "/complete"
    assert (
        owner.post(
            close, json={"outcome": "An unverified assertion of business success."}
        ).status_code
        == 409
    )
    owner.post(
        "/api/ops/missions/" + value["id"] + "/submit-actions",
        json={"operation_ids": [operation["id"]], "acknowledge_review": True},
    )
    reviewer.post(
        "/api/ops/operations/" + operation["id"] + "/decision", json={"decision": "approve"}
    )
    assert (
        owner.post(
            close, json={"outcome": "The work item exists but has not been completed."}
        ).status_code
        == 409
    )
    item = owner.get("/api/ops/work-items").json()[0]
    owner.put(
        "/api/ops/work-items/" + item["id"],
        json={
            "status": "done",
            "outcome": "Reviewed the evidence and confirmed accountable operational ownership.",
        },
    )
    assert (
        owner.post(
            close,
            json={
                "outcome": "Confirmed support ownership and recorded the agreed operational procedure change."
            },
        ).status_code
        == 200
    )
    assert (
        "Owner-recorded outcome" in owner.get("/api/ops/missions/" + value["id"] + "/export").text
    )


def test_withdrawn_drafts_do_not_execute(app, owner):
    value = mission(owner)
    operation = run(owner, value)["operations"][0]
    assert owner.post("/api/ops/operations/" + operation["id"] + "/withdraw").status_code == 200
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkItem)) == 0


def test_competing_workers_claim_one_mission(app, owner):
    value = mission(owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: process_mission(app.state.factory, app.state.settings, value["id"]),
                range(2),
            )
        )
    assert sum(results) == 1
    result = owner.get("/api/ops/missions/" + value["id"]).json()
    assert result["completed_agents"] == 6 and len(result["operations"]) == 1


def test_budget_failure_is_persisted_before_more_model_calls(app, owner, monkeypatch):
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "test-model",
            "api_key": "fake-provider-secret-for-test",
        },
    )
    calls = []

    def fake(settings, agent, payload):
        calls.append(agent.role)
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    result = run(owner, mission(owner, "ai", max_tokens=12000))
    assert result["status"] == "failed" and result["error_code"] == "mission_budget_exhausted"
    assert result["reserved_tokens"] <= 12000 and len(calls) <= 1


def test_expired_worker_lease_recovers(app, owner):
    value = mission(owner)
    with app.state.factory.begin() as db:
        record = db.get(Mission, value["id"])
        record.status = "running"
        record.lease_id = "lost-worker"
        record.lease_until = time.time() - 1
    assert process_mission(app.state.factory, app.state.settings, value["id"])
    assert owner.get("/api/ops/missions/" + value["id"]).json()["completed_agents"] == 6


def test_external_delivery_timeout_is_uncertain_and_not_retried(app, owner, monkeypatch):
    from aivora.operations.connectors import UncertainDelivery
    from aivora.operations.execution import execute_operation

    value = mission(owner)
    operation = run(owner, value)["operations"][0]
    reviewer = member(app, owner, "reviewer@acme.test", "reviewer")
    reviewer_id = reviewer.get("/api/me").json()["user"]["id"]
    connector_id = owner.post(
        "/api/ops/connectors",
        json={
            "name": "Issue tracker",
            "kind": "github",
            "config": {"repository": "sample/operations"},
            "token": "fake-test-connector-token",
        },
    ).json()["id"]
    with app.state.factory.begin() as db:
        op = db.get(Operation, operation["id"])
        op.kind = "github_issue"
        op.connector_id = connector_id
        op.connector_revision = 1
        op.reviewer_id = reviewer_id
        op.status = "approved"
        args = json.loads(op.arguments_json)
        args.update(kind="github_issue", connector_id=connector_id)
        op.arguments_json = json.dumps(args, sort_keys=True, separators=(",", ":"))
        op.arguments_hash = hashlib.sha256(op.arguments_json.encode()).hexdigest()
    calls = []

    def uncertain(*args):
        calls.append(1)
        raise UncertainDelivery("Simulated uncertain response")

    monkeypatch.setattr("aivora.operations.execution.execute_external", uncertain)
    assert not execute_operation(app.state.factory, app.state.settings, operation["id"])
    assert not execute_operation(app.state.factory, app.state.settings, operation["id"])
    assert len(calls) == 1
    with app.state.factory() as db:
        assert db.get(Operation, operation["id"]).status == "uncertain"


def test_model_configuration_cannot_silently_change_a_mission(owner):
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "test-model",
            "api_key": "fake-provider-secret-for-test",
        },
    )
    value = mission(owner, "ai")
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "different-model",
            "api_key": "fake-replacement-secret-test",
        },
    )
    result = run(owner, value)
    assert result["status"] == "failed" and result["error_code"] == "model_configuration_changed"


def test_unknown_sources_and_nonplanner_actions_are_rejected():
    researcher = DEFAULT_TEAM.definition.agents[1]
    payload = {"evidence": [], "departments": ["General"], "connectors": []}
    output = AgentOutput(
        summary="A test output",
        findings=[
            Finding(
                statement="A false factual claim", category="fact", evidence_ids=["invented-source"]
            )
        ],
    )
    with pytest.raises(agents.InvalidOutput):
        agents.validate_output(output, researcher, payload)


def test_feedback_refinement_preserves_research_and_versions_outputs(owner):
    value = mission(owner)
    run(owner, value)
    response = owner.post(
        "/api/ops/missions/" + value["id"] + "/refine",
        json={
            "feedback": "Focus the proposed follow-up on accountable operations ownership and a measured review process."
        },
    )
    assert response.status_code == 200, response.text
    revised = run(owner, value)
    assert revised["iteration"] == 1 and revised["completed_agents"] == 6
    assert next(a for a in revised["agents"] if a["role"] == "researcher")["attempts"] == 1
    history = owner.get("/api/ops/missions/" + value["id"] + "/artifacts").json()
    assert len(history) == 9
    assert {h["iteration"] for h in history} == {0, 1}
    assert revised["operations"][0]["status"] == "withdrawn"


def test_provider_quota_backoff_preserves_checkpoints_and_refunds_rejected_reservation(
    app, owner, monkeypatch
):
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "test-model",
            "api_key": "fake-provider-secret-for-test",
        },
    )
    deferred = [False]
    calls = []

    def fake(settings, agent, payload):
        calls.append(agent.role)
        if agent.role == "planner" and not deferred[0]:
            deferred[0] = True
            raise agents.ProviderRateLimit(20)
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    value = mission(owner, "ai")
    first = run(owner, value)
    assert first["status"] == "waiting_provider" and first["completed_agents"] == 3
    assert first["model_calls"] == 3 and first["retry_at"] > time.time()
    with app.state.factory.begin() as db:
        db.get(Mission, value["id"]).lease_until = time.time() - 1
    resumed = run(owner, value)
    assert resumed["status"] == "ready" and resumed["model_calls"] == 6
    assert calls.count("coordinator") == 1 and calls.count("planner") == 2


def test_nonplanner_cannot_propose_tool_actions():
    researcher=DEFAULT_TEAM.definition.agents[1]
    payload={"evidence":[],"departments":["General"],"connectors":[]}
    output = AgentOutput(
        summary="A test output",
        actions=[
            ActionDraft(
                title="Unauthorized role action",
                description="This specialist cannot draft work",
                department="General",
            )
        ],
    )
    with pytest.raises(agents.InvalidOutput):
        agents.validate_output(output, researcher, payload)
