"""Repeatable fictional operations case for the dedicated demonstration organizations."""

import hashlib
import json
import uuid

from ..db import Chunk, Document
from .contracts import MissionInput
from .data import read_csv
from .models import Dataset
from .runtime import create_mission

CSV = b"case_id,department,stage,age_hours,handoffs\nDEMO-01,Support,triage,4,0\nDEMO-02,Support,waiting_operations,36,3\nDEMO-03,Operations,in_progress,12,1\nDEMO-04,Support,waiting_operations,48,4\nDEMO-05,Operations,resolved,2,1\nDEMO-06,Support,waiting_customer,20,1\nDEMO-07,Operations,in_progress,30,2\nDEMO-08,Support,triage,6,0\nDEMO-09,Operations,resolved,3,1\nDEMO-10,Support,waiting_operations,60,5\nDEMO-11,Operations,in_progress,18,2\nDEMO-12,Support,waiting_customer,10,1\n"
SOP = """Fictional support operating procedure. Every open case needs an accountable handling team. Support validates the issue and gathers evidence. Operations reviews cases explicitly handed to Operations; waiting_customer is a separate stage and must not be counted as an Operations delay. Case age alone does not prove root cause. Changes to ownership or procedures require review. Record the observed outcome before closing improvement work."""


def seed_operations(db, org, requester, settings):
    data_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "aivora-demo-data:" + org.id))
    if not db.get(Dataset, data_id):
        columns, rows, computed = read_csv(CSV)
        db.add(
            Dataset(
                id=data_id,
                org_id=org.id,
                title="Fictional support operations · 12 cases",
                visibility="organization",
                department="General",
                columns_json=json.dumps(columns),
                rows_json=json.dumps(rows),
                profile_json=json.dumps(computed),
                content_hash=hashlib.sha256(CSV).hexdigest(),
            )
        )
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "aivora-demo-procedure:" + org.id))
    if not db.get(Document, doc_id):
        db.add(
            Document(
                id=doc_id,
                org_id=org.id,
                title="Fictional support handoff procedure",
                visibility="organization",
                department="General",
                content_hash=hashlib.sha256(SOP.encode()).hexdigest(),
            )
        )
        db.flush()
        db.add(Chunk(doc_id=doc_id, page=1, text=SOP))
    db.flush()
    if requester.active:
        create_mission(
            db,
            requester,
            MissionInput(
                title="Investigate cross-team support delays",
                objective="Analyze the fictional support case data and support handoff procedure. Identify observed stage and department bottlenecks, distinguish waiting-customer from waiting-operations, state the limits of the evidence and propose measurable operational follow-up work. Do not invent root cause.",
                team_id="default",
                mode="evidence",
                request_key="seed-operations-case-v2",
                dataset_ids=[data_id],
                group_by="department",
                metric="age_hours",
            ),
            settings,
        )
