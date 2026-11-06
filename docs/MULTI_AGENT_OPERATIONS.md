# AIVORA multi-agent operations

## The problem this release solves

Operational decisions are spread across procedures, spreadsheets, issue trackers and people's follow-up work. An answer alone does not resolve a stalled process. AIVORA maintains the chain from objective to evidence, analysis, proposed work, review, execution receipts and a recorded business outcome.

An example is investigating cross-team support delays. The platform profiles the actual supplied data, researches relevant procedures, identifies what is observable, proposes accountable follow-up work, records a separate approval, creates work items or a configured external action, and tracks completion. It must distinguish evidence from assumptions: aggregate queue data alone cannot prove root cause or reconstruct individual cases.

## Six cooperating specialists

| Agent | Responsibility | Boundary |
| --- | --- | --- |
| Coordinator | Scope questions, success criteria and decision points | No factual findings or executable actions |
| Researcher | Relevant document and issue evidence | No dataset record reconstruction; cannot draft writes |
| Analyst | Server-computed statistics and segment breakdowns | No generated Python/SQL; no invented arithmetic |
| Planner | Prioritized work packages and proposed actions | Only allowed departments, connector IDs and typed actions |
| Reviewer | Inspect findings, assumptions and proposed work | Independent context; cannot execute or erase earlier artifacts |
| Writer | Assemble the decision brief and unresolved concerns | Cannot approve actions or assert operational success |

Research and analysis branch concurrently after coordination. Planning joins their validated outputs. Review follows planning, and the final writer follows review. Agent Studio supports custom names, responsibilities and dependency graphs. The server validates 3–8 unique agents, rejects cycles, requires a reviewer to inspect planners and requires the writer to depend on all agents.

AI mode makes separate real Groq/Gemini calls per specialist. Evidence mode uses deterministic extraction, arithmetic and conservative template work; its interface and reports explicitly say that no AI reasoning or semantic review occurred. A configured model is required for AI mode; it never silently falls back to simulated agents.

## Evidence and business data

Mission creation captures accessible document chunk/version references, selected dataset hashes and selected connector revisions. Each agent and publication step rechecks current requester access. Old outputs, artifact history, exports and draft actions are hidden when required sources disappear or become inaccessible.

CSV tools accept UTF-8, at most 2 MB, 10,000 rows and 60 unique columns. Numeric totals, extrema, means, missing values, category counts, group totals and group percentages are computed by code. The model interprets these results instead of performing unrestricted code execution. Facts require valid source IDs; a numeric check rejects unsupported literals and supports explicit rounding of source decimals. These checks do not establish semantic entailment or catch every incorrect association, so review and human judgment remain necessary.

Data access is at document/dataset and department level. Row-level business-entity permissions inside one CSV are not provided. Do not upload a dataset whose rows need more restrictive policies than the dataset itself.

## Company models and credentials

An administrator configures the organization's provider, model and API key in Agent Studio. Secrets are Fernet-encrypted on the server and excluded from API responses and prompts. Environment-level provider settings remain a development default; organization profiles override them. Profiles are versioned, and a running mission will not silently switch to a different model configuration.

`AIVORA_CREDENTIAL_KEY` can supply a managed Fernet key. Otherwise the local application creates `.aivora-secrets.key` next to its database. The key is excluded from Git. Database backups also need the matching key; the local backup command copies it into the backup directory when file-based key management is used. A configured environment key must be backed up independently through the secret-management system.

## Durable execution and recovery

The worker acquires a mission lease, then persists each specialist's validated result and immutable artifact version before dependants continue. Concurrent workers cannot both claim the same mission. On restart, completed stages are reused rather than calling the model again. Failed stages have bounded attempts. Missions also enforce conservative token reservations and a model-call limit.

HTTP 429 is treated as quota deferral. The rejected reservation is refunded, completed checkpoints remain and the worker resumes after backoff. A provider-rejected response contract receives bounded stage retries with validation feedback; other provider errors stop the mission with a visible code. A single request that exceeds the provider account quota fails explicitly rather than repeatedly waiting. Model output that fails schema, source, role or numeric checks is not published. A mission cannot assume success from an interrupted stage.

The bounded graph is reconstructed from the snapshotted team definition. SQL agent steps are the durable checkpoints; this release does not claim to use a hosted LangGraph checkpoint service.

## Feedback, artifacts and outcomes

Before sharing actions, the owner can refine a ready plan with human feedback, up to two rounds. Research/analysis checkpoints are reused; planning, review, writing and their dependants are requeued. Old private drafts are withdrawn. Earlier artifacts remain available by round and content hash. Submitted or dispatched actions cannot silently change under a new plan.

Draft actions are private. The owner reviews exact arguments and explicitly shares selected actions with authorized approvers. A separate reviewer decides; requester self-approval is denied. Argument hashes, expiry, current requester/reviewer access and connector revisions are checked before execution.

Internal work creation and its receipt are committed atomically. GitHub issues and Slack messages use a durable dispatch marker, fixed configured destinations and correlation IDs. A timeout or crash after dispatch becomes **uncertain**, not automatically retried. External exactly-once delivery is not claimed. Scope live credentials to the intended repository/channel and validate them in a sandbox account before adoption.

The work board records planned/in-progress/blocked/done status and concrete outcomes. The mission owner can close an objective only when proposals are settled and internal work is done. The closing outcome is explicitly owner-recorded; it is not an AI assertion that the business achieved a metric. Reopening completed work reopens the mission.

## Start from existing company systems

- **REST:** `missions:read` / `missions:write` plus `knowledge:read`; identities and organization IDs come from the token owner.
- **Local MCP:** discover agent teams, queue a mission and read its private status/artifacts. No approval tool is exposed.
- **Recurring missions:** save mission inputs and an interval. Each run is a new, idempotently queued mission under the owner's current permissions. Invalid schedules pause.
- **Signed incoming hooks:** external systems send `event_id` and `context`, signed with HMAC-SHA256 over `timestamp + "." + raw_body`. The server validates signature, a five-minute timestamp window, exact-payload idempotency and current owner permissions. Event content is untrusted context, not authorization.

The generic mission engine is industry-neutral. GitHub and Slack are implemented adapters; other systems can submit signed events or use REST/MCP, and additional tool adapters require explicit resource and permission mappings. Universal compatibility is not assumed.

## Reproducible demonstration

Run `python -m aivora.seed`, then `python -m aivora.worker`. The dedicated fictional technology and education organizations receive an operations procedure, a 12-case dataset and a queued evidence-mode mission. Random account passwords are printed only on first creation. Re-running the seed preserves existing accounts and does not duplicate missions or resources.

For an opt-in real model test, run `python scripts/live_mission_check.py --model openai/gpt-oss-20b` with `PYTHONPATH=src`. Enter the key through hidden input. It uses a temporary synthetic organization/database and does not submit external actions. Do not put keys in CLI arguments or CI logs.

## Deployment limits

This release is substantially broader than the v0.1 knowledge pilot, but enterprise deployment still requires PostgreSQL RLS/migrations, enterprise identity/recovery, shared traffic controls, indexed retrieval at scale, isolated ingestion, operational telemetry and independent deployment/security validation. Production mode remains gated. A successful model run or test suite is not certification of enterprise security or business impact.
