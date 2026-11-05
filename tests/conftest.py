import pytest
from fastapi.testclient import TestClient

from aivora.api import create_app
from aivora.config import Settings

PASSWORD = "test-only-password-12345"


def register(client, email="owner@acme.test", organization="Acme Studio"):
    response = client.post(
        "/api/auth/signup",
        json={
            "name": "Workspace Owner",
            "organization": organization,
            "email": email,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    client.headers["x-csrf-token"] = response.json()["csrf"]
    return client


def member(app, owner, email, role="employee", department="General"):
    invited = owner.post(
        "/api/invites", json={"email": email, "role": role, "department": department}
    )
    assert invited.status_code == 201, invited.text
    client = TestClient(app)
    accepted = client.post(
        "/api/auth/accept-invite",
        json={
            "email": email,
            "name": "Team Member",
            "password": PASSWORD,
            "token": invited.json()["token"],
        },
    )
    assert accepted.status_code == 201, accepted.text
    client.headers["x-csrf-token"] = accepted.json()["csrf"]
    return client


def upload(
    client,
    text,
    title="Team guide",
    visibility="organization",
    department="General",
    replace_id="",
):
    return client.post(
        "/api/documents",
        data={
            "title": title,
            "visibility": visibility,
            "department": department,
            "replace_id": replace_id,
        },
        files={"file": ("guide.md", text.encode(), "text/markdown")},
    )


@pytest.fixture
def app(tmp_path):
    application = create_app(
        Settings(database_url="sqlite:///" + (tmp_path / "test.db").as_posix())
    )
    yield application
    application.state.engine.dispose()


@pytest.fixture
def owner(app):
    with TestClient(app) as client:
        yield register(client)
