"""Durable, local automations. No arbitrary code or external delivery."""

import time

from sqlalchemy import select, update

from .db import Action, Audit, Automation, AutomationRun, Document, Task


def run_due(factory, org_id=None, now=None):
    now = time.time() if now is None else now
    completed = []
    with factory() as db:
        query = select(Automation).where(Automation.enabled.is_(True), Automation.next_run <= now)
        if org_id:
            query = query.where(Automation.org_id == org_id)
        ids = [row.id for row in db.scalars(query)]
    for automation_id in ids:
        with factory.begin() as db:
            item = db.get(Automation, automation_id)
            scheduled = item.next_run
            # Compare-and-swap claims the schedule inside the same transaction as effects.
            claimed = db.execute(
                update(Automation)
                .where(
                    Automation.id == item.id,
                    Automation.enabled.is_(True),
                    Automation.next_run == scheduled,
                    Automation.next_run <= now,
                )
                .values(next_run=now + item.interval_hours * 3600)
            ).rowcount
            if not claimed:
                continue
            count = 0
            if item.kind == "document_review":
                candidates = db.scalars(
                    select(Document).where(
                        Document.org_id == item.org_id,
                        Document.created <= now - 30 * 86400,
                    )
                )
                for doc in candidates:
                    # A document version generates one review task, even across schedule retries.
                    key = f"review:{doc.id}:v{doc.version}"
                    if not db.scalar(
                        select(Task.id).where(Task.org_id == item.org_id, Task.dedupe_key == key)
                    ):
                        db.add(
                            Task(
                                org_id=item.org_id,
                                title="Review a document older than 30 days",
                                source_type="document",
                                source_id=doc.id,
                                dedupe_key=key,
                            )
                        )
                        count += 1
            else:
                candidates = db.scalars(
                    select(Action).where(
                        Action.org_id == item.org_id,
                        Action.status == "pending",
                        Action.created <= now - 24 * 3600,
                        Action.expires > now,
                    )
                )
                for action in candidates:
                    key = "approval:" + action.id
                    if not db.scalar(
                        select(Task.id).where(Task.org_id == item.org_id, Task.dedupe_key == key)
                    ):
                        db.add(
                            Task(
                                org_id=item.org_id,
                                title="Approval waiting for more than 24 hours",
                                source_type="action",
                                source_id=action.id,
                                dedupe_key=key,
                            )
                        )
                        count += 1
            summary = f"Created {count} internal follow-up task(s)"
            run = AutomationRun(
                automation_id=item.id,
                org_id=item.org_id,
                scheduled_for=scheduled,
                summary=summary,
            )
            db.add(run)
            db.add(
                Audit(
                    org_id=item.org_id,
                    user_id="scheduler",
                    event="automation.executed",
                    object_id=item.id,
                )
            )
            completed.append({"automation_id": item.id, "summary": summary})
    return completed
