# AIVORA

**Organization knowledge. Accountable action.**

A self-hosted AI workspace for organizations that lose time finding trusted information, routing service requests and chasing overdue approvals. Companies configure their own departments, knowledge and request categories rather than receiving a fintech-specific assistant.

**v0.1: working local pilot.** The application, automation worker, MCP integration, tests and container setup are included. The enterprise target architecture is broader than this release: production hardening, enterprise SSO and external SaaS connectors remain explicitly tracked work.

## Working capabilities

- Isolated organization workspaces with employee, reviewer and administrator memberships; single-use, email-bound invitations and credential revocation on membership changes.
- PDF/Markdown/text ingestion with organization, department or administrator visibility; version replacement and deletion.
- A bounded **LangGraph** retrieval/answer/verification graph with citations and private conversations. Old answers are hidden when their sources change or become inaccessible.
- Offline source extraction and configurable **Groq/Gemini** generation. BM25 retrieval works without downloads; optional sentence-transformers add local semantic ranking.
- Configurable HR, IT, operations or facilities requests. A separate reviewer approves immutable arguments, creating an internal ticket atomically. Track and resolve tickets.
- Persistent document-review and overdue-approval schedules, deduplicated internal tasks and execution history.
- Scoped, expiring, revocable **REST API tokens** and a **local stdio MCP bridge**. MCP can propose requests but cannot approve them.
- Real run timings, reported tokens, persisted daily request quotas and redacted audit events. Password changes revoke all old credentials.

Internal tickets and tasks are real persisted records. External Jira tickets, messages and access grants are not executed by this release.

## Run

Requires Python 3.11+. Node is development-only; the UI needs no build step.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
.\run.ps1
```

If script execution is restricted, use these commands without changing system policy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m uvicorn aivora.main:app --host 127.0.0.1 --port 8090
```

Linux/macOS: `sh run.sh`.

Open **http://127.0.0.1:8090** and create a workspace. API reference: `/docs`; health: `/api/health`.

Optional demo seed, after installation:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m aivora.seed
```

This creates fictional technology and education organizations, documents, employee/admin accounts, pending requests and schedules. Random passwords are printed once; existing demo accounts are unchanged.

Run unattended automations in a second terminal:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m aivora.worker
```

## Cloud generation

In the ignored `.env`, set `AIVORA_PROVIDER=groq` and `GROQ_API_KEY`, or `AIVORA_PROVIDER=gemini` and `GOOGLE_API_KEY`. Set `AIVORA_MODEL` to an available model ID for your account and restart. Questions and retrieved passages are sent to that provider.

Adapters have mocked contract tests; live-account inference is separate validation. Offline mode returns labeled source passages, not LLM-generated answers. No supplied API keys are stored in this repository or its runtime configuration.

## Container pilot

```text
docker compose up --build -d
```

Web binds to loopback port 8090. The scheduler shares a durable database volume. This is a trusted local pilot; `AIVORA_ENV=production` deliberately refuses startup until the [production gates](docs/OPERATIONS.md) are implemented and validated.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/evaluate.py
.\.venv\Scripts\python.exe tests/mcp_e2e.py
.\.venv\Scripts\python.exe tests/browser_e2e.py
node --check src/aivora/static/app.js
```

Browser tests use installed Chrome or Playwright Chromium (`python -m playwright install chromium`). Tests use temporary databases and synthetic data. They do not contact company systems. GitHub Actions defines Windows/Linux backend checks and a Linux browser flow. See [validation evidence](docs/VALIDATION.md) for checks actually run.

## Guides

| Guide | Purpose |
| --- | --- |
| [Adoption](docs/ADOPTION.md) | Fit AIVORA into processes and existing applications |
| [Implemented architecture](docs/IMPLEMENTATION.md) | Shipped design, code map and tradeoffs |
| [Operations](docs/OPERATIONS.md) | Scheduler, backup, privacy and production requirements |
| [MCP](docs/MCP.md) | Connect an MCP-capable client |
| [Roadmap](docs/ROADMAP.md) | Status of the broader architecture |
| [Architecture target](docs/ARCHITECTURE.md) | Full enterprise proposal; not a shipped-feature claim |
| [References](docs/REFERENCES.md) | PDF and LISA architectural lessons |

## Boundaries

This is independently implemented in a separate repository. Existing LARK/LISA files were read-only references; no company source or customer data was copied. Local private data is ignored under `data/`. A OneDrive checkout follows its existing synchronization policy; set a different `AIVORA_DATABASE_URL` if needed.

Database RLS, pgvector indexes, enterprise OIDC/SSO, Redis caching/shared rate limits, OpenTelemetry export, hosted OAuth MCP and live Jira/Slack connectors are **not implemented**. Retrieval scans the accessible corpus in process; enterprise-scale capacity has not been established. Trademark availability has not been checked.
