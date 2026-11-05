# AIVORA — Enterprise AI Workspace

An industry-independent AI workspace where companies connect knowledge, enforce employee permissions, and execute approved workflows with measurable quality and cost.

**Status:** product and architecture planning. Application implementation has not started. Working name; repository and trademark availability have not been checked.

Suggested GitHub repository: `aivora`.

## Product journey

1. A company owner creates an organization, configures branding, invites employees and assigns departments and roles.
2. An administrator uploads documents and sets their visibility; ingestion records versions, extraction status and indexing failures.
3. Employees ask questions and receive streamed answers with links to source passages they can access.
4. Employees request an action, such as opening an IT ticket. The system proposes typed arguments, checks permissions and requests approval where appropriate.
5. An authorized reviewer approves; the worker executes once, records the result and updates the conversation.
6. Administrators inspect quality evaluations, request traces, audit events, latency and usage.

Start with fictional HR, IT and operations datasets for two different companies. Add industries through configuration and connectors, not company-specific branches.

## Documents

- [Architecture, security boundaries and stack](docs/ARCHITECTURE.md)
- [Implementation milestones and acceptance criteria](docs/ROADMAP.md)
- [Reference assessment and PDF coverage](docs/REFERENCES.md)

## Repository boundaries

This directory is a separate project. Existing LARK, LISA, LANCE and job-pilot directories are read-only references. Do not copy private source, credentials, customer records or company documents into this repository. Use independently implemented code and synthetic demonstration data.

No API keys are stored here. Configure credentials through ignored local environment files or deployment secrets. Keys shared in chat should be replaced before long-term use. The project must support offline fixtures for tests and explicit provider configuration for live inference.
