"""Create synthetic demo organizations. Never imports LARK/LISA company data."""

import hashlib
import secrets
import time

from sqlalchemy import select

from .config import Settings
from .db import (
    Action,
    Automation,
    Chunk,
    Document,
    Organization,
    User,
    Workflow,
    database,
)
from .operations.demo import seed_operations
from .security import password_hash

GUIDES = {
    "Employee handbook": "Annual leave allowance is {days} days per calendar year. Request leave through your manager. New employees complete security training and meet their buddy in the first week. Remote work requires manager approval. This is fictional demonstration policy.",
    "IT access guide": "To request software access, open an IT support request with the application name, business reason and required access duration. Never share passwords or API tokens. Report a suspected security incident to the internal security team immediately. A reviewer must approve new access requests. This is fictional demonstration guidance.",
    "Operations playbook": "For equipment, facilities or onboarding support, open an Operations request. Include the location, required date and business impact. The handling team reviews the request and tracks it until resolution. This is fictional demonstration guidance.",
}


def main():
    settings = Settings.from_env()
    if settings.environment != "development":
        raise SystemExit("Synthetic seed is only available in development")
    engine, factory = database(settings.database_url)
    created = []
    with factory.begin() as db:
        for slug, name, industry, days in [
            ("acme", "Acme Studio", "Technology", 21),
            ("northstar", "Northstar Academy", "Education", 12),
        ]:
            existing = db.scalar(select(User).where(User.email == f"admin@{slug}.example"))
            if existing:
                requester = (
                    db.scalar(select(User).where(User.email == f"employee@{slug}.example"))
                    or existing
                )
                seed_operations(db, db.get(Organization, existing.org_id), requester, settings)
                continue
            org = Organization(name=name, industry=industry)
            db.add(org)
            db.flush()
            users = []
            for role, person in [("admin", "Alex Morgan"), ("employee", "Jamie Chen")]:
                password = secrets.token_urlsafe(18)
                user = User(
                    org_id=org.id,
                    name=person,
                    email=f"{role}@{slug}.example",
                    role=role,
                    password=password_hash(password),
                )
                db.add(user)
                db.flush()
                users.append(user)
                created.append((name, user.email, password))
            support = Workflow(
                org_id=org.id,
                name="IT support",
                description="Request software, access or device support.",
                department="IT",
            )
            seed_operations(db, org, users[1], settings)
            db.add_all(
                [
                    support,
                    Workflow(
                        org_id=org.id,
                        name="Operations request",
                        description="Get help with facilities and everyday operations.",
                        department="General",
                    ),
                ]
            )
            db.flush()
            for title, template in GUIDES.items():
                text = template.format(days=days)
                doc = Document(
                    org_id=org.id,
                    title=title,
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    created=time.time() - 31 * 86400
                    if title == "Employee handbook"
                    else time.time(),
                )
                db.add(doc)
                db.flush()
                db.add(Chunk(doc_id=doc.id, page=1, text=text))
            db.add(
                Action(
                    org_id=org.id,
                    user_id=users[1].id,
                    workflow_id=support.id,
                    title="Access to the design workspace",
                    description="Please provide project workspace access for the new onboarding cohort.",
                    idempotency_key="synthetic-demo-access",
                    created=time.time() - 25 * 3600,
                    expires=time.time() + 6 * 86400,
                )
            )
            db.add_all(
                [
                    Automation(
                        org_id=org.id,
                        name="Knowledge review",
                        kind="document_review",
                        interval_hours=24,
                        next_run=time.time(),
                    ),
                    Automation(
                        org_id=org.id,
                        name="Overdue approvals",
                        kind="approval_reminder",
                        interval_hours=1,
                        next_run=time.time(),
                    ),
                ]
            )
    engine.dispose()
    if not created:
        print("Demo organizations already exist. No accounts or passwords changed.")
    else:
        print("Synthetic demo accounts created. Store these generated passwords securely:")
        for name, email, password in created:
            print(f"{name} | {email} | {password}")


if __name__ == "__main__":
    main()
