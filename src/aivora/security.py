import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .db import Audit, Credential, User


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return salt + ":" + key.hex()


def password_matches(password, encoded):
    try:
        salt, expected = encoded.split(":", 1)
        key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
        return hmac.compare_digest(key.hex(), expected)
    except (ValueError, TypeError):
        return False


def issue_session(db, user, response, settings):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(
        Credential(
            id=digest(token),
            user_id=user.id,
            kind="session",
            csrf=csrf,
            scopes="[]",
            expires=time.time() + 43200,
        )
    )
    response.set_cookie(
        "aivora_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    return csrf


@dataclass
class Principal:
    user: User
    credential: Credential


def authenticate(request: Request, db: Session, settings):
    auth = request.headers.get("authorization", "")
    bearer = auth.startswith("Bearer ")
    raw = auth[7:] if bearer else request.cookies.get("aivora_session", "")
    credential = db.get(Credential, digest(raw)) if raw else None
    if (
        not credential
        or credential.expires <= time.time()
        or credential.kind != ("api" if bearer else "session")
    ):
        raise HTTPException(401, "Please sign in again")
    user = db.get(User, credential.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account is inactive")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not bearer:
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), credential.csrf):
            raise HTTPException(403, "Missing or invalid CSRF token")
    return Principal(user, credential)


def require_role(principal, *roles):
    if principal.user.role not in roles:
        raise HTTPException(403, "Your role does not allow this operation")


def require_scope(principal, scope):
    import json

    if principal.credential.kind == "api" and scope not in json.loads(principal.credential.scopes):
        raise HTTPException(403, "API token is missing the required scope")


def browser_only(principal):
    if principal.credential.kind != "session":
        raise HTTPException(403, "Use a browser session for account administration")


def audit(db, user, event, object_id=""):
    # Deliberately do not store prompts, emails, document text or secrets in audit payloads.
    db.add(Audit(org_id=user.org_id, user_id=user.id, event=event, object_id=object_id))
