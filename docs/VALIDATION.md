# Validation evidence

Local verification on 6 November 2026, Windows, Python 3.11.5. Dependencies were installed in AIVORA's isolated `.venv`, not LISA's environment.

| Check | Result |
| --- | --- |
| Backend/security suite | 40 tests passed |
| Synthetic retrieval/ACL evaluations | 12/12 cases passed |
| Real headless Chrome workflow | Passed onboarding, upload, cited Q&A/source preview, employee invitation, requests, separate approval, resolution, schedules, token creation/revocation, settings and audit |
| Responsive interface | Desktop and 390 px mobile screenshots inspected; no horizontal page overflow |
| Real MCP stdio client/server | Passed initialization, tool discovery, ACL-aware search, grounded answer, workflow discovery, idempotent pending proposal and invalid-resource rejection |
| Dependency consistency | `pip check` passed |
| Frontend syntax | Node checks passed |
| Linux container image | Runtime lock installed and images built successfully |
| Compose services | Separate validation web and scheduler started healthy |
| Container HTTP smoke | Passed health, auth, ingestion, LangGraph/citations, automation and audit |
| Cross-login browser isolation | A delayed answer from the previous session cannot enter the next user's chat |
| Separate worker process | A standalone `worker --once` process executes a due schedule against shared durable storage |
| Backup/restore | Included in backend suite; restored database supports login and document reads |

The synthetic benchmark checks expected passages, source IDs, absent evidence and restricted/cross-tenant content. It is not an open-ended answer-quality score. A sample offline run recorded p50 22.245 ms and p95 90.26 ms across only 12 temporary-database requests; these figures are not cloud or production load benchmarks. Full local results are generated into ignored `artifacts/evaluation.json`.

Gemini/Groq request contracts and error/citation handling were tested with mock HTTP responses. No live provider inference, semantic-model download, enterprise identity provider or external SaaS account has been validated. Hosted production, PostgreSQL/RLS, external connectors and independent security review remain outside the verified release.

GitHub Actions workflows are provided for Windows/Linux checks and Linux browser tests. Do not equate a pushed workflow file with a successful hosted CI run; inspect the repository's Actions results for the relevant commit.
