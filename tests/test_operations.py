import pytest
from conftest import PASSWORD, upload
from fastapi.testclient import TestClient

from aivora.api import create_app
from aivora.backup import backup
from aivora.config import Settings


def test_password_change_revokes_old_token_and_preserves_spaces(app, owner):
    token = owner.post(
        "/api/tokens", json={"label": "Portal", "scopes": ["knowledge:read"]}
    ).json()["token"]
    assert (
        owner.post(
            "/api/account/password",
            json={
                "current_password": "wrong-password-123",
                "new_password": "new-test-password-123",
            },
        ).status_code
        == 403
    )
    new_password = "  spaces-are-part-of-password  "
    result = owner.post(
        "/api/account/password", json={"current_password": PASSWORD, "new_password": new_password}
    )
    assert result.status_code == 200
    owner.headers["x-csrf-token"] = result.json()["csrf"]
    assert owner.get("/api/me").status_code == 200
    portal = TestClient(app, headers={"Authorization": "Bearer " + token})
    assert portal.get("/api/documents").status_code == 401
    anon = TestClient(app)
    assert (
        anon.post(
            "/api/auth/login", json={"email": "owner@acme.test", "password": new_password.strip()}
        ).status_code
        == 401
    )
    assert (
        anon.post(
            "/api/auth/login", json={"email": "owner@acme.test", "password": new_password}
        ).status_code
        == 200
    )


def test_backup_restore_roundtrip(app, owner, tmp_path):
    upload(owner, "Annual leave allowance is 21 days.")
    source = app.state.engine.url.database
    target = tmp_path / "restored.db"
    backup(source, target)
    with pytest.raises(FileExistsError):
        backup(source, target)
    restored = create_app(Settings(database_url="sqlite:///" + target.as_posix()))
    client = TestClient(restored)
    login = client.post("/api/auth/login", json={"email": "owner@acme.test", "password": PASSWORD})
    assert login.status_code == 200
    client.headers["x-csrf-token"] = login.json()["csrf"]
    assert client.get("/api/documents").json()[0]["title"] == "Team guide"
    restored.state.engine.dispose()


def test_production_does_not_silently_start_local_pilot(monkeypatch):
    monkeypatch.setenv("AIVORA_ENV", "production")
    with pytest.raises(ValueError):
        Settings.from_env()
