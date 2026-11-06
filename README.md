# AIVORA

**An organization-neutral multi-agent operations platform.**

AIVORA takes a business objective through research, quantitative analysis, operational planning, independent review, approved execution and recorded outcomes. Organizations configure specialist teams, connect their own knowledge/data/tools, inspect versioned artifacts and run missions manually, on a schedule or from signed business events.

**v0.2: multi-agent operations release.** Six specialist agents run as a configurable LangGraph dependency graph, with parallel research/analysis, durable checkpoints, bounded budgets, quota backoff, human feedback and versioned artifacts. The browser includes Mission Control, Agent Studio, Business Data, Connected Tools, Action Approvals, Work Board and Mission Triggers, alongside the earlier knowledge workspace.

Example objective: **“Investigate support bottlenecks from our procedures and operational data, quantify what is observable, propose a cross-department improvement plan, create approved follow-up work and record what changed.”** The same engine supports incident investigations, launch coordination, onboarding and management reviews through configurable teams and mission templates.

AI mode makes separate real model calls for the specialists. Evidence mode is explicitly deterministic and does not claim AI reasoning. A real six-agent Groq mission has been exercised using fictional data. This is a self-hosted application release, not a claim of audited enterprise production readiness; SSO, database RLS and deployment/load hardening remain tracked requirements.

## Working capabilities

- Configurable specialist teams with a real coordinator → parallel research/analysis → planner → reviewer → writer graph. The coordinator selects typed read tools; code resolves authorized resources.
- Private missions, durable agent checkpoints, quota backoff, bounded budgets, failure recovery, feedback refinement and immutable artifact history.
- CSV analysis with code-computed metrics and grouped breakdowns; no model-generated Python/SQL executes.
- Owner-reviewed drafts, separate approver decisions, internal work items, recorded outcomes and explicit objective closure.
- GitHub/Slack adapters with encrypted credentials, fixed destinations, immutable arguments and uncertain-delivery reconciliation.
- Recurring missions and signed, idempotent incoming event hooks for existing systems.
- Isolated organization workspaces with employee, reviewer and administrator memberships; single-use, email-bound invitations and credential revocation on membership changes.
- PDF/Markdown/text ingestion with organization, department or administrator visibility; version replacement and deletion.
- A bounded **LangGraph** retrieval/answer/verification graph with citations and private conversations. Old answers are hidden when their sources change or become inaccessible.
- Offline source extraction and configurable **Groq/Gemini** generation. BM25 retrieval works without downloads; optional sentence-transformers add local semantic ranking.
- Configurable HR, IT, operations or facilities requests. A separate reviewer approves immutable arguments, creating an internal ticket atomically. Track and resolve tickets.
- Persistent document-review and overdue-approval schedules, deduplicated internal tasks and execution history.
- Scoped, expiring, revocable **REST API tokens** and a **local stdio MCP bridge**. MCP can propose requests but cannot approve them.
- Real run timings, reported tokens, persisted daily request quotas and redacted audit events. Password changes revoke all old credentials.

Internal tickets/work items are real persisted records. Configured GitHub and Slack adapters can perform real HTTP actions after approval; live external accounts were not used during verification. Jira and access-provisioning connectors are not provided. See [the complete operations guide](docs/MULTI_AGENT_OPERATIONS.md).

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

This creates fictional technology and education organizations, procedures, a 12-case operations dataset, six-agent evidence-mode missions, employee/admin accounts, pending requests and schedules. Random passwords are printed once; existing accounts are unchanged. `python scripts/demo_check.py` verifies repeatability and the independent worker without printing credentials.

Run unattended automations in a second terminal:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m aivora.worker
```

## Cloud generation

Configure the organization's provider, model ID and API key in **Agent Studio**. Credentials are encrypted server-side and versioned. The ignored `.env` can alternatively provide development defaults: `AIVORA_PROVIDER=groq` / `GROQ_API_KEY`, or `gemini` / `GOOGLE_API_KEY`, plus `AIVORA_MODEL`. Selected questions, evidence and agent context are sent to that provider.

Six actual Groq specialists have completed a synthetic mission, including checkpointed quota recovery. Gemini remains contract-tested rather than live-validated. The opt-in `scripts/live_mission_check.py` uses hidden key input and a temporary synthetic organization. Evidence mode is deterministic and never presented as AI reasoning. No supplied API keys are committed or retained in this checkout's runtime configuration.

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
.\.venv\Scripts\python.exe scripts/demo_check.py
.\.venv\Scripts\python.exe tests/mcp_e2e.py
.\.venv\Scripts\python.exe tests/browser_e2e.py
node --check src/aivora/static/app.js
```

Browser tests use installed Chrome or Playwright Chromium (`python -m playwright install chromium`). Tests use temporary databases and synthetic data. They do not contact company systems. GitHub Actions defines Windows/Linux backend checks and a Linux browser flow. See [validation evidence](docs/VALIDATION.md) for checks actually run.

## Guides

| Guide | Purpose |
| --- | --- |
| [Adoption](docs/ADOPTION.md) | Fit AIVORA into processes and existing applications |
| [Multi-agent operations](docs/MULTI_AGENT_OPERATIONS.md) | Objective-to-outcome system, recovery and integrations |
| [LISA lessons](docs/LISA_LESSONS.md) | How actual startup patterns informed the generalized design |
| [Implemented architecture](docs/IMPLEMENTATION.md) | Shipped design, code map and tradeoffs |
| [Operations](docs/OPERATIONS.md) | Scheduler, backup, privacy and production requirements |
| [MCP](docs/MCP.md) | Connect an MCP-capable client |
| [Roadmap](docs/ROADMAP.md) | Status of the broader architecture |
| [Architecture target](docs/ARCHITECTURE.md) | Full enterprise proposal; not a shipped-feature claim |
| [References](docs/REFERENCES.md) | PDF and LISA architectural lessons |

## Boundaries

This is independently implemented in a separate repository. Existing LARK/LISA files were read-only references; no company source or customer data was copied. Local private data is ignored under `data/`. A OneDrive checkout follows its existing synchronization policy; set a different `AIVORA_DATABASE_URL` if needed.

Database RLS, pgvector indexes, enterprise OIDC/SSO, shared Redis traffic controls, OpenTelemetry export, hosted OAuth MCP and a Jira connector are **not implemented**. GitHub/Slack adapters are implemented and contract-tested; live-account validation remains required for your targets. Retrieval scans the accessible corpus in process; enterprise-scale capacity has not been established. Trademark availability has not been checked.
