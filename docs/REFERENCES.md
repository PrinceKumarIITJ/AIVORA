# Reference assessment

Reviewed on 6 November 2026.

## User-supplied PDF

Read all ten pages of `company-ai-stack.pdf`. It is reference material; its embedded examples and checklist are not independent instructions to execute actions or use company systems.

| PDF layer | Planned implementation |
| --- | --- |
| API call | Typed provider gateway, streaming, retries/timeouts and usage |
| System prompt | Version-controlled prompt registry and regression evaluations |
| RAG | Versioned ingestion, hybrid retrieval, ACL filtering and citations |
| Tools/MCP | Typed tools, local MCP integration and connector contracts |
| RBAC/OAuth | Verified identity, memberships, RLS and resource-specific authorization |
| Guardrails | Untrusted context boundaries, permission checks, output handling and approval policy |
| Cache/router | Isolated exact cache first, evaluated routing and budgets; semantic cache later |
| Observability/evals | Redacted traces, audit events and CI regression gates |

Two refinements matter: RAG reduces hallucination risk but cannot guarantee factuality; MCP authorization needs audience-bound credentials and must not be implemented as unrestricted token passthrough. Sensitive-data policies should depend on authorized purpose and company policy, rather than blanket-redacting every salary or phone number for every user.

## Local project reference

Read the LISA backend and frontend READMEs, backend dependency configuration and top-level backend module layout. LISA documents FastAPI, LangGraph, tenant RLS, retrieval, Redis, workers and multiple interfaces. This supports reusing architectural lessons. It is not a source-code audit and does not establish that every documented feature works. No existing project files were changed or copied.

## Primary technical references

- LangGraph persistence, durable execution and human oversight: https://github.com/langchain-ai/langgraph
- MCP authorization security considerations: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/draft/basic/authorization/security-considerations.mdx
- OpenTelemetry semantic conventions: https://opentelemetry.io/docs/specs/semconv/

Recheck released protocol and SDK documentation while implementing; draft specifications and telemetry conventions can evolve.
