"""Verify repeatable fictional seed data and the separate worker without printing passwords."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import func, select

from aivora.db import database
from aivora.operations.models import AgentStep, Dataset, Mission, Operation


def main():
    with tempfile.TemporaryDirectory(prefix="aivora-demo-check-") as temp:
        url = "sqlite:///" + (Path(temp) / "demo.db").as_posix()
        env = {
            **os.environ,
            "AIVORA_DATABASE_URL": url,
            "AIVORA_ENV": "development",
            "AIVORA_PROVIDER": "extractive",
            "PYTHONPATH": str(Path("src").resolve()),
        }
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, "-m", "aivora.seed"],
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if result.returncode:
                raise RuntimeError("Synthetic seed failed: " + result.stderr[-800:])
        result = subprocess.run(
            [sys.executable, "-m", "aivora.worker", "--once"],
            env=env,
            text=True,
            capture_output=True,
            timeout=40,
        )
        if result.returncode:
            raise RuntimeError("Worker failed: " + result.stderr[-800:])
        engine, factory = database(url)
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(Mission)) == 2
            assert db.scalar(select(func.count()).select_from(Dataset)) == 2
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AgentStep)
                    .where(AgentStep.status == "completed")
                )
                == 12
            )
            assert (
                db.scalar(
                    select(func.count()).select_from(Operation).where(Operation.status == "draft")
                )
                == 2
            )
        engine.dispose()
    print(
        "PASS: idempotent seed, two fictional industries, two isolated missions, twelve agent checkpoints and draft-only work packages processed by a separate worker"
    )


if __name__ == "__main__":
    main()
