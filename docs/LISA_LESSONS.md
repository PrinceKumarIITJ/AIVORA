# Architectural lessons from the LARK/LISA reference

The existing startup projects were inspected read-only. This release independently implements generalized patterns; no company customer records, credentials, production API calls or proprietary source were imported into the public repository.

| Reference pattern inspected | Why it matters | AIVORA application |
| --- | --- | --- |
| Partner planner separates capability selection from caller identity | A model may select a task but must not invent tenant/customer authority | Agent output schemas cannot select user/organization identity; the server checks scoped resources |
| Structured session memory tracks an active subject, candidates and pending work | Durable state is more useful than blindly resending a transcript | Mission objective, source manifests, agent checkpoints, feedback rounds and explicit action states |
| Customer 360 combines multiple subject-specific reads | Operational context comes from more than one document | Research and analysis combine authorized procedures, business datasets and selected tool context |
| Journey/funnel tools expose where work is waiting | A generic answer does not identify a process bottleneck | Validated CSV segment breakdowns, separate observations/causes and trackable follow-up proposals |
| Numeric answer guards use retrieved facts | Plausible numbers can be operationally harmful | Code-computed metrics plus source-ID and numeric-reference validation |
| Read-only tool registries and fixed endpoints | Authorization must remain outside the language model | Fixed-destination connector adapters, department access and mandatory approval for writes |
| Turn traces and user-facing cards expose evidence and execution | Users need to inspect what happened and act on it | Agent DAG, evidence ledger, artifact history, approval hash, receipts and work outcomes |

These are architectural lessons, not a claim that the reference implementation was fully audited or that its fintech behavior was ported. In particular, AIVORA adds a separate controlled execution lifecycle instead of copying a domain-specific loan assistant or making calls to LARK systems.
