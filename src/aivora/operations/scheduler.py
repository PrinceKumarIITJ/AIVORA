import json
import time

from sqlalchemy import select, update

from ..db import Audit, User
from .contracts import MissionInput
from .models import MissionSchedule
from .runtime import create_mission


def run_mission_schedules(factory, settings, now=None):
    now = time.time() if now is None else now
    with factory() as db:
        ids = list(
            db.scalars(
                select(MissionSchedule.id)
                .where(MissionSchedule.enabled.is_(True), MissionSchedule.next_run <= now)
                .limit(20)
            )
        )
    queued = 0
    for schedule_id in ids:
        try:
            with factory.begin() as db:
                schedule = db.get(MissionSchedule, schedule_id)
                scheduled = schedule.next_run
                claimed = db.execute(
                    update(MissionSchedule)
                    .where(
                        MissionSchedule.id == schedule.id,
                        MissionSchedule.enabled.is_(True),
                        MissionSchedule.next_run == scheduled,
                        MissionSchedule.next_run <= now,
                    )
                    .values(next_run=now + schedule.interval_hours * 3600)
                ).rowcount
                if not claimed:
                    continue
                user = db.get(User, schedule.user_id)
                if not user or not user.active:
                    raise ValueError("Schedule owner is inactive")
                template = json.loads(schedule.mission_template_json)
                template["request_key"] = f"schedule:{schedule.id}:{int(scheduled)}"
                mission = create_mission(db, user, MissionInput.model_validate(template), settings)
                db.add(
                    Audit(
                        org_id=schedule.org_id,
                        user_id=user.id,
                        event="mission_schedule.triggered",
                        object_id=mission.id,
                    )
                )
                queued += 1
        except Exception:
            with factory.begin() as db:
                schedule = db.get(MissionSchedule, schedule_id)
                if schedule:
                    schedule.enabled = False
                    db.add(
                        Audit(
                            org_id=schedule.org_id,
                            user_id=schedule.user_id,
                            event="mission_schedule.disabled_invalid_context",
                            object_id=schedule.id,
                        )
                    )
    return queued
