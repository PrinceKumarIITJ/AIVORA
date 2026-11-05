"""Deterministic synthetic evidence/ACL benchmark; not an LLM quality claim."""

import json
import math
import platform
import statistics
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from aivora.api import create_app
from aivora.config import Settings
from aivora.db import Chunk, Document


def main():
    cases = json.loads(Path("evals/cases.json").read_text(encoding="utf-8"))
    results = []
    with tempfile.TemporaryDirectory(prefix="aivora-eval-") as temp:
        app = create_app(Settings(database_url="sqlite:///" + (Path(temp) / "eval.db").as_posix()))
        owner = TestClient(app)
        body = {
            "name": "Eval Owner",
            "organization": "Synthetic Studio",
            "email": "owner@eval.test",
            "password": "synthetic-eval-password-1",
        }
        signup = owner.post("/api/auth/signup", json=body)
        assert signup.status_code == 201
        owner.headers["x-csrf-token"] = signup.json()["csrf"]
        org_id = owner.get("/api/me").json()["organization"]["id"]
        invite = owner.post("/api/invites", json={"email": "employee@eval.test"}).json()["token"]
        employee = TestClient(app)
        signup = employee.post(
            "/api/auth/accept-invite",
            json={
                "name": "Eval Employee",
                "email": "employee@eval.test",
                "password": "synthetic-eval-password-2",
                "token": invite,
            },
        )
        employee.headers["x-csrf-token"] = signup.json()["csrf"]
        other = TestClient(app)
        signup = other.post(
            "/api/auth/signup",
            json={**body, "email": "owner@other.test", "organization": "Synthetic Academy"},
        )
        other.headers["x-csrf-token"] = signup.json()["csrf"]
        with app.state.factory.begin() as db:
            for title, text, visibility, department in [
                (
                    "Leave policy",
                    "Annual leave allowance is 21 days per year. वार्षिक अवकाश 21 दिन है।",
                    "organization",
                    "General",
                ),
                (
                    "IT access guide",
                    "To request software access, include the application name and business reason. A reviewer approves access.",
                    "organization",
                    "General",
                ),
                (
                    "Onboarding",
                    "The onboarding checklist includes security training and meeting a buddy in the first week.",
                    "organization",
                    "General",
                ),
                (
                    "Executive compensation",
                    "Executive salary is 900000 fictional credits.",
                    "admin",
                    "General",
                ),
                ("Sales plan", "Sales forecast codename is CITRUS.", "department", "Sales"),
            ]:
                doc = Document(
                    org_id=org_id,
                    title=title,
                    content_hash="synthetic",
                    visibility=visibility,
                    department=department,
                )
                db.add(doc)
                db.flush()
                db.add(Chunk(doc_id=doc.id, page=1, text=text))
        clients = {"owner": owner, "employee": employee, "other": other}
        for case in cases:
            start = time.perf_counter()
            response = clients[case["actor"]].post("/api/chat", json={"question": case["question"]})
            latency = round((time.perf_counter() - start) * 1000, 2)
            answer = response.json()
            passed = response.status_code == 200
            if "contains" in case:
                passed &= case["contains"] in answer.get("answer", "")
            if "forbidden" in case:
                passed &= case["forbidden"] not in answer.get("answer", "")
            if "source" in case:
                passed &= case["source"] in [c["title"] for c in answer.get("citations", [])]
            if case.get("no_sources"):
                passed &= not answer.get("citations")
            results.append(
                {
                    "id": case["id"],
                    "passed": bool(passed),
                    "latency_ms": latency,
                    "retrieved_titles": [c["title"] for c in answer.get("citations", [])],
                }
            )
        app.state.engine.dispose()
    latencies = sorted(r["latency_ms"] for r in results)
    report = {
        "benchmark": "synthetic-extractive-acl-v1",
        "provider": "extractive",
        "retrieval": "bm25",
        "warm_state": "mixed; no answer cache",
        "python": platform.python_version(),
        "os": platform.system(),
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "p50_ms": statistics.median(latencies),
        "p95_ms": latencies[math.ceil(len(latencies) * 0.95) - 1],
        "results": results,
        "limitations": "Small synthetic regression set. Checks expected passages, ACL isolation and abstention; does not measure open-ended cloud answer quality or production load.",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/evaluation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"results", "limitations"}}, indent=2
        )
    )
    for row in results:
        if not row["passed"]:
            print("FAIL:", row["id"])
    if report["passed"] != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
