# Validation evidence

Local v0.2 verification on 6 November 2026, Windows, Python 3.11.5. Dependencies were installed in AIVORA's isolated `.venv`, not LISA's environment. All verification data is synthetic.

| Check | Observed result |
| --- | --- |
| Backend/security/reliability suite | 70 tests passed |
| Synthetic retrieval/ACL evaluations | 12/12 cases passed; this is not an open-ended reasoning score |
| Actual headless Chrome workflow | Passed onboarding, knowledge ingestion/citations, CSV upload, six evidence-mode agent stages, exact draft submission, separate approval, persisted work completion, observed outcome and objective closure |
| Other browser workflows | Passed invitations, employee requests, tickets, recurring missions, token creation/revocation, settings, audit and delayed-response isolation across logins |
| Responsive UI | Desktop and 390 px mobile checks; no horizontal page overflow; actual mission screenshot generated under ignored artifacts |
| Actual MCP stdio client/server | Passed initialization, seven-tool discovery, ACL-aware search/answer, idempotent request proposal, team discovery, mission creation and owner-private mission status |
| Separate worker process | Processed two isolated six-stage missions across fictional technology/education organizations; repeated seeding did not duplicate resources |
| Concurrency/recovery | Tested concurrent mission leases, expired lease recovery, actual parallel research/analysis, checkpoint reuse, bounded contract retry with feedback, quota deferral/refund and budget rejection before provider calls |
| Permission/action boundaries | Tested dataset/source restrictions, owner-private mission output, model identity changes, rejected unauthorized agent actions, immutable approvals, uncertain delivery without blind retry and correlated receipt recovery |
| Feedback/history | Tested retained research checkpoints, regenerated planning/review/writing and immutable artifact versions |
| Signed events/schedules | Tested HMAC authentication, payload-bound replay/idempotency and durable recurring mission creation |
| Backup/restore | Restored login/documents and encrypted organization model credentials with the matching backup key |
| Dependency/format checks | `pip check`, Ruff and frontend Node syntax checks passed |
| Linux container image and Compose | Isolated validation web/worker images built; both services healthy |
| Real container HTTP | Passed auth, ingestion, cited knowledge answer, dataset upload, six-stage operations mission, automation and audit |

## Real provider inference

A real Groq `openai/gpt-oss-20b` mission completed all six distinct specialists using a fictional procedure and three-row business dataset: six accepted model calls, 21,110 reported input tokens, 3,571 output tokens and six private action drafts. The provider's 8,000-token/minute account quota caused intermediate deferrals; completed checkpoints were retained and the mission resumed. The reviewer returned concerns, leaving the result in `review_required` rather than implying business approval.

Live testing also exposed and drove fixes for malformed response contracts, unsupported finding categories, numerical validation and provider quota handling. A successful run is execution evidence, not an agent-quality benchmark or a guarantee that future stochastic outputs will succeed. The opt-in `scripts/live_mission_check.py` reproduces this using hidden credential input and a temporary database; no external actions are submitted.

Gemini is contract-tested, not live-validated. GitHub/Slack fixed-destination requests and receipt reconciliation use HTTP contract tests, not live external accounts. Internal work, approvals and outcomes use actual database writes and the browser/API lifecycle.

## Interpretation and limits

The retrieval evaluation checks expected passages, source IDs, absent evidence and restricted/cross-tenant content. Its generated latency measurements cover only twelve temporary-database requests and are not cloud or production load benchmarks. Full local results are generated into ignored `artifacts/evaluation.json`.

Evidence mode is deterministic and does not claim AI reasoning or independent semantic review. AI source-ID and numeric checks do not prove full semantic entailment. Live inference does not certify business impact or security.

Hosted enterprise identity, PostgreSQL/RLS, enterprise-scale capacity, external SaaS account permissions and independent security review remain outside this verified release. Production startup remains gated until the documented requirements are met.

GitHub Actions runs Windows/Linux backend checks and a Linux browser flow. Inspect [Actions](https://github.com/PrinceKumarIITJ/AIVORA/actions) for the exact commit; the presence of a workflow file alone is not a successful hosted run.
