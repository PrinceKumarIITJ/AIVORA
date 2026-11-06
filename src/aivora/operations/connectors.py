"""Fixed-destination, scoped connector adapters. Credentials never enter agent prompts."""

import json
import os
import re
from functools import lru_cache
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url


class ConnectorError(Exception):
    pass


class UncertainDelivery(ConnectorError):
    pass


@lru_cache(maxsize=8)
def cipher(database_url, configured_key=""):
    if configured_key:
        return Fernet(configured_key.encode())
    database = make_url(database_url).database
    if not database or database == ":memory:":
        return Fernet(Fernet.generate_key())
    path = Path(database).resolve().parent / ".aivora-secrets.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ConnectorError("Secret key file must not be a symbolic link")
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        key = path.read_bytes()
    else:
        key = Fernet.generate_key()
        with os.fdopen(fd, "wb") as output:
            output.write(key)
    return Fernet(key)


def encrypt(settings, secret):
    return cipher(settings.database_url, settings.credential_key).encrypt(secret.encode()).decode()


def decrypt(settings, ciphertext):
    return (
        cipher(settings.database_url, settings.credential_key).decrypt(ciphertext.encode()).decode()
    )


def allowed(connector, user):
    return (
        connector.org_id == user.org_id
        and connector.enabled
        and connector.department in {"General", user.department}
    )


def validate_config(kind, config):
    if kind == "github":
        if set(config) != {"repository"} or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", config.get("repository", "")
        ):
            raise ValueError("GitHub requires a fixed owner/repository")
    elif kind == "slack":
        if set(config) != {"channel"} or not re.fullmatch(
            r"[CG][A-Z0-9]{5,30}", config.get("channel", "")
        ):
            raise ValueError("Slack requires one fixed channel ID")
    else:
        raise ValueError("Unsupported connector type")


def read_context(settings, connector):
    config = json.loads(connector.config_json)
    if connector.kind != "github":
        return {"kind": "slack", "note": "Write-only destination; no channel history is ingested"}
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                f"https://api.github.com/repos/{config['repository']}/issues",
                params={"state": "open", "per_page": 30},
                headers={
                    "Authorization": "Bearer " + decrypt(settings, connector.secret_ciphertext),
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            issues = response.json()
            if not isinstance(issues, list):
                raise ConnectorError("Unexpected connector response")
            return {
                "kind": "github",
                "repository": config["repository"],
                "issues": [
                    {
                        "number": i.get("number"),
                        "title": str(i.get("title", ""))[:300],
                        "body": str(i.get("body") or "")[:1000],
                        "url": i.get("html_url"),
                    }
                    for i in issues
                    if "pull_request" not in i
                ],
            }
    except (httpx.HTTPError, ValueError, KeyError):
        raise ConnectorError("Connector read failed; check its configured permissions") from None


def execute_external(settings, connector, operation_id, arguments):
    config = json.loads(connector.config_json)
    token = decrypt(settings, connector.secret_ciphertext)
    if connector.kind == "github":
        url = f"https://api.github.com/repos/{config['repository']}/issues"
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        body = {
            "title": arguments["title"],
            "body": arguments["description"] + f"\n\n<!-- aivora-operation:{operation_id} -->",
        }
    else:
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": "Bearer " + token}
        body = {
            "channel": config["channel"],
            "text": arguments["title"] + "\n" + arguments["description"],
            "client_msg_id": operation_id,
        }
    try:
        with httpx.Client(timeout=25, follow_redirects=False, trust_env=False) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError:
        raise UncertainDelivery("Delivery outcome is unknown; reconcile before any retry") from None
    if response.status_code >= 500 or response.is_redirect:
        raise UncertainDelivery("Connector returned an uncertain delivery outcome")
    if not response.is_success:
        raise ConnectorError("Connector rejected the approved action")
    try:
        result = response.json()
        if connector.kind == "slack":
            if not result.get("ok"):
                raise ConnectorError("Slack rejected the approved message")
            return {"channel": config["channel"], "timestamp": result["ts"]}
        return {"number": result["number"], "url": result["html_url"]}
    except (ValueError, KeyError):
        raise UncertainDelivery(
            "Connector accepted a request but returned no verifiable receipt"
        ) from None
