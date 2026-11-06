# Operations and production gates

v0.2 adds the multi-agent runtime described in [Multi-agent operations](MULTI_AGENT_OPERATIONS.md). The worker now checks queues every two seconds, runs due mission schedules, processes leased agent graphs and dispatches approved actions. The older document-review/approval-reminder automations remain available. GitHub/Slack writes use durable dispatch records and correlated-receipt reconciliation; they are no longer merely planned adapters.

## Processes and schedules

Run the web process with `python -m uvicorn aivora.main:app --host 127.0.0.1 --port 8090` and the worker separately with `python -m aivora.worker`, with `PYTHONPATH=src`.

The worker polls every 30 seconds. It advances a claimed schedule and saves its effects in the same transaction. `--once` processes one iteration. Missed intervals coalesce into one catch-up run. Schedules persist through restarts.

Document reviews create one task per version older than 30 days. Approval reminders create one task per pending, unexpired request older than 24 hours. These are internal follow-ups, not delivered notifications. Completing a task does not rewrite or republish a policy.

## Backup and restore

```text
python -m aivora.backup --output data/backups/workspace.db
```

The command uses SQLite's online backup API, verifies integrity and refuses to overwrite an existing path. Backups include documents, conversations and credential hashes; store them with restricted access and encryption.

To restore, stop web/worker processes and point `AIVORA_DATABASE_URL` to a copy of the verified backup. Restart and verify login, document access and pending requests. Unexpired credentials are restored too; decide whether an incident recovery requires their invalidation. The automated restore test uses a separate database and verifies login/document persistence.

## Current limits

- File limits: 5 MB, 150 PDF pages and 500,000 extracted characters. Parsing is synchronous and not resource-isolated.
- Authentication limits are process-local. Chat quotas persist and are reserved before inference; failed attempts count. Quotas reset at UTC midnight.
- Provider destinations are fixed, redirects disabled and connection/read timeouts configured. No blind provider retries/fallback.
- SSE delivers an answer after validation; it is not provider token streaming. The browser uses JSON responses.
- Conversations store user content intentionally. Audit/run payloads omit raw content. No retention scheduler exists.
- Startup creates the initial schema with SQLAlchemy; Alembic upgrades/rolling schema changes are not supported yet.

## Production gates

`AIVORA_ENV=production` intentionally refuses startup. The following remain deployment requirements even though v0.2 has a complete functional mission lifecycle. Before real production traffic, implement and independently validate:

1. PostgreSQL migrations, non-owner role, FORCE RLS and tenant context across requests/workers, with negative tests.
2. Enterprise OIDC/SSO, verified membership provisioning, recovery and applicable MFA/session policies.
3. Shared limits/concurrency/token budgets, streaming capacity and realistic load/soak benchmarks.
4. Isolated asynchronous ingestion, safe parsers, required OCR/scanning, object storage and retention controls.
5. Persistent hybrid indexes, multilingual relevance benchmarks and calibrated evaluations for chosen live models.
6. TLS, origins, secure cookies, secret management, network policies, encrypted backups and incident/restore exercises.
7. Redacted telemetry export, operational alerts and external immutable audit retention where required.
8. Per external connector: delegated authorization, scoped refresh/revocation, outbox/reconciliation and sandbox live tests.
9. For hosted MCP: released transport/authorization compliance, audience validation and protocol conformance tests. Stdio is a different deployment boundary.
10. Dependency/security review, verified CI, organization-specific data processing review and a support owner.

These are engineering requirements for further development, not additional approval gates. v0.1 is a controlled local pilot; it is not an audited enterprise deployment.
