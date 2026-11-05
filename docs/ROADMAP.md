# Implementation roadmap

All milestones below are pending. Build vertical slices with working UI, API, persistence and tests before adding another layer.

| Milestone | Deliverable | Acceptance evidence |
| --- | --- | --- |
| 1. Foundation | Monorepo, Docker Compose, API/web skeleton, CI, migrations, synthetic seed | Clean-machine startup; API health and database readiness; locked dependencies |
| 2. Organizations and identity | OIDC login, invitations, departments, role policy, tenant RLS | Two organizations cannot access each other's records; expired tokens and forged tenant IDs denied |
| 3. Knowledge ingestion | Upload UI, private storage, worker, extraction, document versions, ACLs | Upload to searchable document; failed job recovery; version replacement and deletion remove stale content |
| 4. Grounded chat | Hybrid retrieval, source drawer, streaming, persisted conversations, Gemini/Groq gateway | Answers cite accessible passages; unknown-policy questions abstain; provider failures display recoverable errors |
| 5. Approved actions | Typed IT-ticket service, approval inbox, durable graph checkpoints, action ledger | Restart during approval resumes correctly; repeated approval produces one ticket; revoked permission prevents execution |
| 6. MCP and connectors | Standards-compliant local MCP integration, connector registry and scoped authorization | Audience/scope checks, invalid argument rejection and transport contract tests; real external connector tested separately |
| 7. Reliability and governance | Budgets, limits, evaluated routing, cache isolation, redacted traces and audit UI | Budget concurrency test; provider timeout recovery; cache never crosses authorization boundaries |
| 8. Evaluations and delivery | Dataset, CI quality gates, deployment docs, backup/restore and portfolio demo | Reproducible quality/latency/cost report and end-to-end demo from fresh setup |

## Evaluation plan

Create a versioned synthetic benchmark covering HR policy Q&A, IT procedures, operations documents, conflicting versions, absent evidence, Hindi/English questions, unauthorized salary access, cross-tenant requests, indirect injection, tool argument manipulation, duplicate approvals and interrupted workflows.

Use deterministic checks for authorization, valid citations, prohibited actions and duplicate writes. Measure retrieval recall@k against labeled relevant chunks. Evaluate groundedness and answer usefulness with calibrated human review and optional model judging; retain judge version and disagreement examples. Compare routes and models on the same dataset. Report sample count, environment, warm/cold status and p50/p95 latency; do not advertise invented savings or accuracy.

Hard CI gates: zero known tenant/ACL leaks, zero unauthorized tool executions, valid cited source IDs and successful migration/integration tests. Establish measured retrieval and answer-quality thresholds after the first baseline; changes must not silently lower them.

## Portfolio deliverables

- A five-minute demo: onboard two companies, upload different policies, answer with citations, deny unauthorized access, approve an IT ticket and inspect its trace.
- Architecture diagram and decision records explaining pgvector versus a separate vector database, deterministic workflows versus agents, and exact versus semantic caching.
- Failure demonstration: interrupt a worker, resume an approval and prove the action is not duplicated.
- Public synthetic evaluation set, CI results and a measured performance report with hardware and model configuration.
- Setup guide, API documentation, threat model, deployment runbook and an honest implemented/planned feature matrix.

Resume claims should describe implemented capabilities and measured results only. Suggested eventual wording: "Built a multi-tenant enterprise AI workspace with permission-aware hybrid retrieval, source citations, durable approval workflows and automated security/quality evaluations." Add metrics only after measurement.

## Next handoff

Create an empty GitHub repository named `aivora` (or provide a preferred name) and share its URL. Implementation can continue locally without GitHub access; remote pushes require a configured authenticated account. No existing project repository should be reused or modified.
