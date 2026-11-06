import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from conftest import upload
from test_operations_platform import dataset, mission, run

from aivora.config import Settings
from aivora.operations import agents
from aivora.operations.connectors import (
    encrypt,
    execute_external,
    reconcile_external,
    validate_config,
)
from aivora.operations.contracts import ReadRequest


def test_provider_contract_retry_is_bounded_and_receives_feedback(owner, monkeypatch):
    owner.put(
        "/api/ops/model",
        json={"provider": "groq", "model": "test-model", "api_key": "fake-contract-retry-secret"},
    )
    calls = []

    def fake(settings, agent, payload):
        calls.append(agent.role)
        if agent.role == "coordinator" and calls.count("coordinator") == 1:
            error = agents.AgentError("Include all required fields")
            error.code = "provider_contract_error"
            raise error
        if agent.role == "coordinator":
            assert "required fields" in payload["validation_feedback"]
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    result = run(owner, mission(owner, "ai"))
    assert result["status"] == "ready", result
    assert calls.count("coordinator") == 2 and len(calls) == 7


@pytest.mark.parametrize("kind", ["github", "slack"])
def test_fixed_destination_action_contracts(kind, monkeypatch):
    settings = Settings(database_url="sqlite:///:memory:")
    config = {"repository": "sample/operations"} if kind == "github" else {"channel": "C123456789"}
    connector = SimpleNamespace(
        kind=kind,
        config_json=json.dumps(config),
        secret_ciphertext=encrypt(settings, "fake-scoped-connector-secret"),
    )
    original = httpx.Client

    def handler(request):
        assert (
            request.method == "POST"
            and request.headers["authorization"] == "Bearer fake-scoped-connector-secret"
        )
        body = json.loads(request.content)
        assert "fake-scoped-connector-secret" not in request.content.decode()
        if kind == "github":
            assert str(request.url) == "https://api.github.com/repos/sample/operations/issues"
            assert "aivora-operation:test-operation-id" in body["body"]
            return httpx.Response(
                201,
                json={"number": 12, "html_url": "https://github.com/sample/operations/issues/12"},
            )
        assert (
            str(request.url) == "https://slack.com/api/chat.postMessage"
            and body["channel"] == "C123456789"
        )
        assert body["client_msg_id"] == "test-operation-id"
        return httpx.Response(200, json={"ok": True, "ts": "123.456"})

    monkeypatch.setattr(
        "aivora.operations.connectors.httpx.Client",
        lambda **kw: original(transport=httpx.MockTransport(handler)),
    )
    result = execute_external(
        settings,
        connector,
        "test-operation-id",
        {"title": "A reviewed action", "description": "Exact approved work details"},
    )
    assert result.get("number") == 12 if kind == "github" else result.get("timestamp") == "123.456"


def test_reconciliation_requires_unique_correlated_receipt(monkeypatch):
    settings = Settings(database_url="sqlite:///:memory:")
    connector = SimpleNamespace(
        kind="github",
        config_json=json.dumps({"repository": "sample/operations"}),
        secret_ciphertext=encrypt(settings, "fake-scoped-connector-secret"),
    )
    original = httpx.Client
    responses = [
        [],
        [
            {
                "number": 22,
                "html_url": "https://github.com/sample/operations/issues/22",
                "body": "<!-- aivora-operation:operation-22 -->",
            }
        ],
    ]
    monkeypatch.setattr(
        "aivora.operations.connectors.httpx.Client",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=responses.pop(0))
            )
        ),
    )
    assert reconcile_external(settings, connector, "operation-22") is None
    assert reconcile_external(settings, connector, "operation-22")["number"] == 22
    with pytest.raises(ValueError):
        validate_config("github", {"repository": "../.."})


def test_coordinator_can_expand_only_authorized_read_context(app, owner, monkeypatch):
    upload(
        owner,
        "COPPER procedures require an assigned owner and written escalation evidence.",
        "COPPER protocol",
    )
    value = dataset(owner)
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "test-model",
            "api_key": "fake-provider-secret-for-test",
        },
    )
    seen = []

    def fake(settings, agent, payload):
        seen.append((agent.role, payload))
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        if agent.role == "coordinator":
            output.tool_requests = [
                ReadRequest(tool="knowledge.search", query="COPPER escalation"),
                ReadRequest(
                    tool="dataset.group", dataset_id=value["id"], group_by="status", metric="hours"
                ),
            ]
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    result = run(owner, mission(owner, "ai", dataset_ids=[value["id"]]))
    assert result["status"] == "ready", result
    assert any(e["event"] == "tool.completed" for e in result["events"])
    research = next(p for role, p in seen if role == "researcher")
    assert all(e["type"] in {"document", "connector"} for e in research["evidence"])
    assert "COPPER" in str(research["evidence"])
    analytical = next(p for role, p in seen if role == "analyst")
    computed = next(e for e in analytical["evidence"] if e["type"] == "dataset")["agent_analyses"][
        0
    ]
    assert computed["groups"][0]["total"] == "20"


def test_research_and_analysis_are_actually_concurrent(owner, monkeypatch):
    owner.put(
        "/api/ops/model",
        json={
            "provider": "groq",
            "model": "test-model",
            "api_key": "fake-provider-secret-for-test",
        },
    )
    barrier = threading.Barrier(2)

    def fake(settings, agent, payload):
        if agent.role in {"researcher", "analyst"}:
            barrier.wait(timeout=5)
        output, tokens = agents.evidence_agent(agent, payload)
        output.verdict = "pass"
        return output, (20, 10)

    monkeypatch.setattr(agents, "complete_agent", fake)
    assert run(owner, mission(owner, "ai"))["status"] == "ready"
