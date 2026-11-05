# Adopting AIVORA

Start with one repeated knowledge question and one repeatable request process.

| Organization | Knowledge problem | Workflow | Automation |
| --- | --- | --- | --- |
| Software company | Finding access procedures | Software access request | Overdue approval follow-up |
| School/university | Finding staff handbook policies | Facilities support | Review outdated procedures |
| Manufacturing office | Locating team procedures | Equipment support | Follow up pending requests |
| Professional services | Repeated onboarding questions | Operations assistance | Review onboarding knowledge |

These are adoption examples, not integrations with HRIS, student systems or machinery. Safety-critical or regulated applications need additional validation.

## Organization setup

1. Create the workspace and choose its industry and assistant name. No fintech concepts are hardcoded.
2. Assign at least two people: a requester and a separate reviewer/administrator.
3. Invite staff using standardized department names; names are currently case-sensitive.
4. Upload a small authoritative document set. Include effective dates and policy owners in the text.
5. Verify visibility with employee accounts. Administrator role does not bypass another department's document restriction.
6. Configure workflows and handling departments. Reviewers handle their department or General workflows. Administrators can review other users' requests across departments.
7. Enable document reviews and approval reminders. Run the worker and inspect its execution history.
8. Measure time-to-answer and time-waiting-for-review against a baseline before claiming improvement.

## Existing application integration

Your existing application's backend can call REST endpoints regardless of its frontend framework. Use a scoped token belonging to the actual user, not one broad administrator key for everybody.

```python
import os
import httpx

# Server-side example: credential must belong to the actual employee.
response = httpx.post(
    os.environ['AIVORA_API_URL'] + '/api/chat',
    headers={'Authorization': 'Bearer ' + os.environ['AIVORA_API_TOKEN']},
    json={'question': 'How do I request software access?'},
    timeout=60,
)
response.raise_for_status()
answer = response.json()
```

Knowledge Q&A requires `knowledge:read` and `chat:write`. Proposing requests uses `workflows:read` and `actions:write`; tracking uses `actions:read`. The token owner's current membership determines organization and permissions. API tokens cannot approve requests.

User-managed credentials suit a controlled pilot. Delegated SSO and short-lived per-user token exchange remain required for broad production integration.

## Real-document behavior

Extracted text is stored as database chunks; original uploaded files are not retained. Replacement publishes a new version and removes old chunks atomically. Deletion removes chunks and hides historical answers that relied on those sources. OCR, malware scanning, retention automation and automatic source synchronization are not included.

Cloud models receive questions and accessible retrieved passages. Optional local semantic encoding happens on the host after downloading its model. Choose a processing mode that meets your organization's data requirements.

## Pilot acceptance

Verify two organizations and three roles: a correct cited answer, unknown evidence, unauthorized source access, revoked membership, approved/rejected requests, duplicate retry and automation task completion. Assign document/support owners before expanding the pilot.
