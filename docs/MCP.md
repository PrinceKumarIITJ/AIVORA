# Local MCP integration

The stdio bridge lets an MCP-capable application find accessible knowledge, ask questions, discover workflows and propose pending requests through the same authorization checks as the web app.

Start AIVORA, sign in as the actual user and create a minimally scoped token in Integrations. Configure the MCP client to launch the project's Python environment with `-m aivora.mcp_server`. Set `PYTHONPATH` to the absolute `src` directory and supply `AIVORA_API_URL=http://127.0.0.1:8090` plus the user's `AIVORA_API_TOKEN` using the client's secret/environment settings. Never commit tokens.

| Tool | Scopes | Effect |
| --- | --- | --- |
| `search_knowledge` | `knowledge:read` | ACL-filtered passages |
| `ask_knowledge` | `knowledge:read`, `chat:write` | Private Q&A persistence; consumes quota |
| `list_workflows` | `workflows:read` | Organization request categories |
| `propose_request` | `actions:write` | Pending proposal; stable caller-generated key required for retries |
| `list_agent_teams` | `missions:read`, `knowledge:read` | Discover configured specialist teams |
| `start_mission` | `missions:write`, `knowledge:read` | Queue a private, bounded multi-agent objective |
| `mission_status` | `missions:read`, `knowledge:read` | Read owner-scoped outputs, source ledger and action receipts |

User input cannot choose a destination URL, organization ID or role. The bridge permits local HTTP or configured HTTPS. Tools do not approve, delete, run shell commands or make arbitrary HTTP calls. A proposal is not an executed ticket: a separate reviewer decides in AIVORA.

This is local stdio with a purpose-issued AIVORA credential, not a remote OAuth server. The integration test initializes real MCP client/server subprocesses, exercises tools against a temporary HTTP service and verifies that repeated proposals produce one pending request and no executed ticket.
