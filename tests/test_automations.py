import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from aivora.automation import run_due
from aivora.db import Action, Automation, Document
from conftest import member, upload
from test_workflows import propose


def schedule(owner, kind="document_review"):
    r = owner.post("/api/automations", json={"name": "Follow up", "kind": kind, "interval_hours": 24})
    assert r.status_code == 201
    return r.json()["id"]


def test_document_review_automation_deduplicates_tasks(app, owner):
    doc = upload(owner, "Annual leave policy needs a review.").json()["id"]
    with app.state.factory.begin() as db:
        db.get(Document, doc).created = time.time() - 31 * 86400
    item = schedule(owner)
    assert len(owner.post("/api/automations/run").json()["runs"]) == 1
    data = owner.get("/api/automations").json()
    assert len(data["tasks"]) == 1 and len(data["runs"]) == 1
    assert owner.post("/api/automations/run").json()["runs"] == []
    with app.state.factory.begin() as db:
        db.get(Automation, item).next_run = time.time() - 1
    owner.post("/api/automations/run")
    data = owner.get("/api/automations").json()
    assert len(data["tasks"]) == 1 and len(data["runs"]) == 2
    task_id = data["tasks"][0]["id"]
    assert owner.post("/api/tasks/" + task_id + "/complete").status_code == 200
    assert owner.get("/api/automations").json()["tasks"][0]["status"] == "completed"


def test_overdue_approval_automation(app, owner):
    employee = member(app, owner, "employee@acme.test")
    action = propose(employee).json()
    with app.state.factory.begin() as db:
        db.get(Action, action["id"]).created = time.time() - 25 * 3600
    schedule(owner, "approval_reminder")
    owner.post("/api/automations/run")
    tasks = owner.get("/api/automations").json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["source_id"] == action["id"]
    assert employee.get("/api/automations").status_code == 403


def test_paused_automation_does_not_run(app, owner):
    item = schedule(owner)
    assert owner.post("/api/automations/" + item + "/toggle").json()["enabled"] is False
    assert owner.post("/api/automations/run").json()["runs"] == []


def test_parallel_schedulers_claim_once(app, owner):
    schedule(owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_due, app.state.factory) for _ in range(2)]
        result = [f.result() for f in futures]
    assert sum(map(len, result)) == 1
    assert len(owner.get("/api/automations").json()["runs"]) == 1
