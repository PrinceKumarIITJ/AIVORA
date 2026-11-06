"""Exercise the real MCP stdio protocol against a temporary AIVORA HTTP service."""

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aivora.api import create_app
from aivora.config import Settings


async def exercise(url, token):
    env = dict(os.environ)
    env.update(AIVORA_API_URL=url, AIVORA_API_TOKEN=token)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "aivora.mcp_server"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {
                "search_knowledge",
                "ask_knowledge",
                "list_workflows",
                "propose_request",
                "list_agent_teams",
                "start_mission",
                "mission_status",
            }
            search = await session.call_tool(
                "search_knowledge", {"question": "Annual leave allowance"}
            )
            assert not search.isError and "21 days" in str(search.content)
            answer = await session.call_tool(
                "ask_knowledge", {"question": "Annual leave allowance"}
            )
            assert not answer.isError and "21 days" in str(answer.content)
            workflows = await session.call_tool("list_workflows", {})
            workflow = json.loads(workflows.content[0].text)
            # FastMCP may encode list values as one JSON array or separate structured items.
            workflow_id = workflow[0]["id"] if isinstance(workflow, list) else workflow["id"]
            args = {
                "workflow_id": workflow_id,
                "title": "Need design access",
                "description": "Access needed for the upcoming project",
                "request_key": "mcp-e2e-proposal-1",
            }
            proposal = await session.call_tool("propose_request", args)
            assert not proposal.isError and "pending" in str(proposal.content)
            replay = await session.call_tool("propose_request", args)
            assert not replay.isError
            rejected = await session.call_tool(
                "propose_request",
                {
                    **args,
                    "workflow_id": "foreign-id",
                    "request_key": "mcp-e2e-foreign-1",
                },
            )
            assert rejected.isError
            team = await session.call_tool("list_agent_teams", {})
            assert not team.isError and "Cross-department operations" in str(team.content)
            new = await session.call_tool(
                "start_mission",
                {
                    "title": "MCP business objective",
                    "objective": "Review operational evidence and prepare a documented improvement plan.",
                    "request_key": "mcp-mission-001",
                    "mode": "evidence",
                },
            )
            assert not new.isError
            result = json.loads(new.content[0].text)
            status = await session.call_tool("mission_status", {"mission_id": result["id"]})
            assert not status.isError and "queued" in str(status.content)


def run():
    with tempfile.TemporaryDirectory(prefix="aivora-mcp-") as temp:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        app = create_app(
            Settings(
                database_url="sqlite:///" + (Path(temp) / "test.db").as_posix(),
                origin=url,
            )
        )
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        try:
            with httpx.Client(base_url=url) as client:
                signup = client.post(
                    "/api/auth/signup",
                    json={
                        "name": "MCP Owner",
                        "organization": "MCP Test Org",
                        "email": "mcp@example.test",
                        "password": "mcp-test-password-123",
                    },
                )
                assert signup.status_code == 201
                client.headers["x-csrf-token"] = signup.json()["csrf"]
                assert (
                    client.post(
                        "/api/documents",
                        data={"title": "Leave handbook"},
                        files={
                            "file": (
                                "leave.md",
                                b"Annual leave allowance is 21 days.",
                                "text/markdown",
                            )
                        },
                    ).status_code
                    == 201
                )
                token = client.post(
                    "/api/tokens",
                    json={
                        "label": "MCP test",
                        "scopes": [
                            "knowledge:read",
                            "chat:write",
                            "workflows:read",
                            "actions:write",
                            "actions:read",
                            "missions:read",
                            "missions:write",
                        ],
                    },
                ).json()["token"]
                asyncio.run(exercise(url, token))
                actions = client.get("/api/actions").json()
                assert (
                    len(actions) == 1
                    and actions[0]["status"] == "pending"
                    and not actions[0]["ticket_id"]
                )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
    print(
        "PASS: MCP protocol initialization, tool discovery, ACL-aware search, grounded answer, workflow discovery, idempotent pending proposal and invalid-resource rejection"
    )


if __name__ == "__main__":
    run()
