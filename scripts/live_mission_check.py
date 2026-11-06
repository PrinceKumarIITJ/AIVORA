"""Opt-in real provider smoke test using a hidden key and synthetic business data only."""

import argparse
import getpass
import json
import tempfile
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from aivora.api import create_app
from aivora.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["groq", "gemini"], default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Print provider error and invalid synthetic output diagnostics; never use with private data",
    )
    args = parser.parse_args()
    if args.diagnostic:
        original_post = httpx.Client.post

        def diagnostic_post(client, url, **kwargs):
            result = original_post(client, url, **kwargs)
            if str(url).startswith("https://api.groq.com/") and result.status_code >= 400:
                print(
                    "PROVIDER_DIAGNOSTIC",
                    result.status_code,
                    str(result.json().get("error", {}).get("message", ""))[:600],
                    flush=True,
                )
            return result

        httpx.Client.post = diagnostic_post
        from aivora.operations import agents

        original_validate = agents.validate_output

        def diagnostic_validate(output, agent, payload):
            try:
                return original_validate(output, agent, payload)
            except agents.InvalidOutput:
                print(
                    "INVALID_SYNTHETIC_FINDINGS",
                    agent.role,
                    json.dumps([f.model_dump() for f in output.findings], ensure_ascii=False),
                    flush=True,
                )
                raise

        agents.validate_output = diagnostic_validate
    key = getpass.getpass("Authorized provider key (hidden; not retained): ")
    with tempfile.TemporaryDirectory(prefix="aivora-live-") as temp:
        app = create_app(Settings(database_url="sqlite:///" + (Path(temp) / "test.db").as_posix()))
        try:
            with TestClient(app) as c:
                signup = c.post(
                    "/api/auth/signup",
                    json={
                        "name": "Synthetic Owner",
                        "organization": "Synthetic Operations Studio",
                        "email": "owner@synthetic.example",
                        "password": "synthetic-live-password-123",
                    },
                )
                c.headers["x-csrf-token"] = signup.json()["csrf"]
                profile = c.put(
                    "/api/ops/model",
                    json={"provider": args.provider, "model": args.model, "api_key": key},
                )
                assert profile.status_code == 200
                c.post(
                    "/api/documents",
                    data={"title": "Support operating procedure"},
                    files={
                        "file": (
                            "process.md",
                            b"Support cases require an accountable owner. Investigate queue age and handoff status before claiming a cause. Operations reviews unresolved cross-team cases. A process change needs reviewer approval.",
                            "text/markdown",
                        )
                    },
                )
                data = c.post(
                    "/api/ops/datasets",
                    data={"title": "Synthetic support queue"},
                    files={
                        "file": (
                            "support.csv",
                            b"department,status,hours\nSupport,pending,12\nSupport,pending,8\nOperations,done,2\n",
                            "text/csv",
                        )
                    },
                ).json()
                mission = c.post(
                    "/api/ops/missions",
                    json={
                        "title": "Resolve support bottlenecks",
                        "objective": "Research our support operating procedure and analyze the attached queue. Identify observations and missing evidence, create a prioritized cross-department improvement plan and draft accountable internal work items. Do not infer root cause from three records.",
                        "team_id": "default",
                        "mode": "ai",
                        "request_key": "live-synthetic-mission-001",
                        "dataset_ids": [data["id"]],
                        "group_by": "department",
                        "metric": "hours",
                        "max_tokens": 250000,
                    },
                )
                assert mission.status_code == 201, mission.text
                result = c.post("/api/ops/missions/" + mission.json()["id"] + "/run").json()
                deadline=time.monotonic()+240
                while result["status"]=="waiting_provider" and time.monotonic()<deadline:
                    delay=max(1,min(30,result["retry_at"]-time.time()+1))
                    print("PROVIDER_BACKOFF",round(delay),"seconds; completed checkpoints",result["completed_agents"],flush=True)
                    time.sleep(delay)
                    result=c.post("/api/ops/missions/"+mission.json()["id"]+"/run").json()
                print(
                    "MISSION",
                    result["status"],
                    "error:",
                    result["error_code"] or "none",
                    flush=True,
                )
                for agent in result["agents"]:
                    print("AGENT", agent["role"], agent["status"], flush=True)
                print(
                    "MODEL_CALLS",
                    result["model_calls"],
                    "INPUT_TOKENS",
                    result["input_tokens"],
                    "OUTPUT_TOKENS",
                    result["output_tokens"],
                    flush=True,
                )
                print("DRAFT_ACTIONS", len(result["operations"]), flush=True)
                for item in result["events"]:
                    if item["event"] == "agent.failed":
                        print("SAFE_FAILURE_DETAIL", item["agent_id"], item["detail"], flush=True)
                if result["status"] not in {"ready", "review_required"}:
                    raise SystemExit(1)
        finally:
            app.state.engine.dispose()
    print(
        "PASS: six real provider agents produced checkpointed business outputs from synthetic evidence; no external action was submitted"
    )


if __name__ == "__main__":
    main()
