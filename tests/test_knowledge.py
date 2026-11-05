from conftest import member, register, upload
from fastapi.testclient import TestClient
from sqlalchemy import select

from aivora.api import create_app
from aivora.config import Settings
from aivora.db import Chunk, Run
from aivora.providers import ProviderUnavailable


def test_grounded_answer_and_source_preview(owner):
    doc = upload(owner, "Annual leave allowance is 21 days per year.", "Leave policy").json()
    result = owner.post("/api/chat", json={"question": "What is the annual leave allowance?"})
    assert result.status_code == 200, result.text
    answer = result.json()
    assert "21 days" in answer["answer"] and "[1]" in answer["answer"]
    assert answer["citations"][0]["document_id"] == doc["id"]
    assert owner.get("/api/documents/" + doc["id"]).json()["chunks"]
    assert owner.get("/api/overview").json()["requests_today"] == 1


def test_unknown_question_abstains(owner):
    upload(owner, "Annual leave allowance is 21 days.")
    answer = owner.post(
        "/api/chat", json={"question": "Quantum unicorn spaceship specification?"}
    ).json()
    assert not answer["citations"] and "enough evidence" in answer["answer"]


def test_conversation_private_to_user(app, owner):
    upload(owner, "Annual leave allowance is 21 days.")
    answer = owner.post("/api/chat", json={"question": "Annual leave?"}).json()
    employee = member(app, owner, "employee@acme.test")
    assert employee.get("/api/conversations").json() == []
    assert employee.get("/api/conversations/" + answer["conversation_id"]).status_code == 404
    assert (
        employee.post(
            "/api/chat",
            json={
                "question": "Annual leave",
                "conversation_id": answer["conversation_id"],
            },
        ).status_code
        == 404
    )


def test_replacement_and_delete_hide_old_answers(app, owner):
    doc = upload(owner, "Annual leave allowance is 21 days.").json()["id"]
    answer = owner.post("/api/chat", json={"question": "Annual leave allowance"}).json()
    assert (
        upload(owner, "Annual leave allowance is now 18 days.", replace_id=doc).json()["version"]
        == 2
    )
    history = owner.get("/api/conversations/" + answer["conversation_id"]).json()
    assert "hidden" in history["messages"][1]["content"]
    assert not history["messages"][1]["citations"]
    current = owner.post("/api/chat", json={"question": "Annual leave allowance"}).json()
    assert "18 days" in current["answer"] and "21 days" not in current["answer"]
    assert owner.delete("/api/documents/" + doc).status_code == 200
    with app.state.factory() as db:
        assert list(db.scalars(select(Chunk))) == []
    assert (
        owner.post("/api/chat", json={"question": "Annual leave allowance"}).json()["citations"]
        == []
    )


def test_access_revocation_hides_historical_answer(app, owner):
    doc = upload(owner, "Annual leave allowance is 21 days.").json()["id"]
    employee = member(app, owner, "employee@acme.test")
    answer = employee.post("/api/chat", json={"question": "Annual leave"}).json()
    upload(owner, "Annual leave allowance is 21 days.", visibility="admin", replace_id=doc)
    assert (
        "hidden"
        in employee.get("/api/conversations/" + answer["conversation_id"]).json()["messages"][1][
            "content"
        ]
    )
    assert employee.get("/api/documents/" + doc).status_code == 404


def test_daily_quota_is_persistent(tmp_path):
    settings = Settings(
        database_url="sqlite:///" + (tmp_path / "quota.db").as_posix(), daily_limit=1
    )
    app = create_app(settings)
    c = register(TestClient(app))
    assert c.post("/api/chat", json={"question": "Hello there"}).status_code == 200
    app2 = create_app(settings)
    c2 = TestClient(app2)
    c2.cookies.update(c.cookies)
    c2.headers.update(c.headers)
    assert c2.post("/api/chat", json={"question": "Another question"}).status_code == 429


def test_provider_failure_recorded_without_leaking_secrets(app, owner, monkeypatch):
    upload(owner, "Annual leave allowance is 21 days.")

    def unavailable(*args):
        raise ProviderUnavailable("Provider unavailable")

    monkeypatch.setattr("aivora.api.generate", unavailable)
    assert owner.post("/api/chat", json={"question": "Annual leave"}).status_code == 503
    with app.state.factory() as db:
        assert db.scalar(select(Run)).status == "provider_error"


def test_event_stream_contract(owner):
    upload(owner, "Annual leave allowance is 21 days.")
    r = owner.post("/api/chat/stream", json={"question": "Annual leave allowance"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: sources" in r.text and "event: delta" in r.text and "event: done" in r.text


def test_upload_validation_and_xss_is_data(owner):
    r = owner.post(
        "/api/documents",
        data={"title": "Executable"},
        files={"file": ("payload.exe", b"not accepted")},
    )
    assert r.status_code == 422
    assert upload(owner, "   ").status_code == 422
    title = '<img src=x onerror="alert(1)">'
    assert upload(owner, "Annual leave allowance is 21 days.", title).status_code == 201
    assert owner.get("/api/documents").json()[0]["title"] == title
    assert "script-src 'self'" in owner.get("/").headers["content-security-policy"]
