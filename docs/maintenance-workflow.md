# Maintenance and repair workflow (M3)

`MaintenanceRequest` is the canonical writable operational record. A linked `MaintenanceIssue` retains its legacy identifier, attachments and update history. The issue API can add shared notes but cannot independently resolve or advance a linked repair; linked status is mirrored only by lifecycle services. Unlinked historical issues remain readable and retain their legacy status workflow. Historical records are not auto-linked by title or date.

## State transitions

| Request | Trigger | Work order | Legacy issue |
| --- | --- | --- | --- |
| `OPEN` | Tenant/staff report | `PENDING` | `OPEN` when linked |
| `IN_PROGRESS` | Staff triage/assignment | `ASSIGNED`, then technician `IN_PROGRESS` | `IN_PROGRESS` |
| `COMPLETED` | Assigned technician submits a structured completion | `COMPLETED` | Remains `IN_PROGRESS` while awaiting verification |
| `CLOSED` | Authorized staff verifies a submitted completion | `COMPLETED` | `RESOLVED` |
| `IN_PROGRESS` | Staff rejects verification with required notes | `IN_PROGRESS` | `IN_PROGRESS`; rejected completion remains in history |
| `CANCELLED` | Authorized staff cancels open/in-progress work with reason | `CANCELLED` | Existing issue status is retained and a cancellation update is appended; legacy issue status has no cancelled value |

Technician assignment history begins `PENDING`. The currently assigned, eligible technician may accept it once, or decline it with a reason. Decline records the response and returns the request to `OPEN` with an unassigned `PENDING` work order; staff must explicitly assign it again. A duplicate accept is idempotent. For compatibility with older clients, starting an unanswered assigned job records acceptance as part of the start action. Reassignments retain each assignment response in history.

There is no separate `TRIAGED` state. Triage is recorded with actor, time, category, notes, algorithm priority and optional safety override. The override requires an attributed reason. When a request explicitly requires quote approval, a safety override permits work to start without an approved quote; the reason is retained on the request and audit event. No spending threshold is implied.

## Authorization and endpoints

- Tenant reports use the existing issue endpoint and must be on the caller's active lease. The tenant account and organization are resolved server-side.
- Property owners, managers and caretakers with maintenance write access can triage, assign, decide quotes, verify/reject completion and cancel.
- Technician assignment requires active organization membership and an active, verified, available profile. The deterministic matching engine gates trade/skills before assignment.
- Only the assigned technician can start work and submit a completion. A verifier must be a different user and have organization maintenance write access.
- Tenant request reads expose approved quotations and repair outcome/resolution, but redact internal triage/verification notes and actual costs. Technicians see only requests visible through their assigned work orders unless separately authorized for organization read.

Primary endpoints under `/api/v1/maintenance/requests/`:

- `POST /` report (staff may include a unit and tenant; tenant identity and active lease remain server-validated).
- `POST /{id}/triage/`, `/assign/`, `/start/`, `/quotations/`, `/quotations/{quote_id}/decision/`, `/complete/`, `/verify/`, `/cancel/`.
- Technician responses use `POST /{id}/accept/` and `POST /{id}/decline/` (decline requires a reason). Authorized property staff schedule a follow-up with `POST /{id}/follow-up/`, passing a future `follow_up_at`, reason and optional `assignee_id` (defaults to the current assignee).
- Existing `/comments/` and `/close/` remain; `close` is a compatibility alias that verifies the latest submitted completion.

Amounts use integer KES cents. Quotation totals and actual totals are derived from their integer components. Decided quotations and submitted completion records are immutable history. A new quotation is a resubmission; a rejected completion remains in history before the technician submits another completion. Optional materials are free-text repair history, not inventory or SKU records.

Follow-up scheduling is allowed only while work is unresolved and its latest completion is `NEEDS_FOLLOW_UP` or was rejected by the verifier. It does not change the repair state or satisfy verification. A new completion supersedes the schedule and records that change in the audit history. Follow-up date, reason and responsible party are available to authorized staff; tenants can see the date and reason but not staff identity.

## Deliberate limits

The product has no vendor settlement, payment, supplier catalog, inventory, asset registry, calendar or reminder subsystem. `NEEDS_FOLLOW_UP` cannot be verified closed; staff must reject it for further work, schedule follow-up if appropriate, and verify a later completion. Tenant feedback is a shared comment and does not independently reopen a verified repair.
