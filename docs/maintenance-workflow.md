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
- `POST /{id}/triage/`, `/assign/`, `/start/`, `/quotations/`, `/quotations/{quote_id}/submit/`, `/quotations/{quote_id}/decision/`, `/complete/`, `/verify/`, `/cancel/`. Itemized quotation drafts can be replaced with `PATCH /{id}/quotations/{quote_id}/` while still in `DRAFT`.
- Technician responses use `POST /{id}/accept/` and `POST /{id}/decline/` (decline requires a reason). Authorized property staff schedule a follow-up with `POST /{id}/follow-up/`, passing a future `follow_up_at`, reason and optional `assignee_id` (defaults to the current assignee).
- Existing `/comments/` and `/close/` remain; `close` is a compatibility alias that verifies the latest submitted completion.

Amounts use integer KES cents. Legacy quotations retain their aggregate labour, materials and other amounts and are never given fabricated line items. New itemized quotations start as drafts; their line totals are calculated as decimal quantity × integer unit price, rounded to the nearest minor unit with `ROUND_HALF_UP`. Material lines roll into the existing materials subtotal; labour lines into labour; transport and other lines into the existing other subtotal. The stored quotation total is derived from those category totals. A draft can be edited only by its submitter. Submission makes its lines and amount immutable; after rejection, a changed quotation is a new revision linked to the prior quote. Decided quotations and submitted completion records are immutable history. Actual costs remain separate from estimates. Optional materials recorded on completions are free-text repair history, not inventory or SKU records.

No configurable expenditure approval ceiling is implemented. The emergency/safety override remains the existing explicit, attributed exception to the “approved quotation before work starts” rule; its broader monetary scope and any approval-limit interaction remain unresolved policy decisions. BOQ support does not establish a spending threshold or change that exception.

Follow-up scheduling is allowed only while work is unresolved and its latest completion is `NEEDS_FOLLOW_UP` or was rejected by the verifier. It does not change the repair state or satisfy verification. A new completion supersedes the schedule and records that change in the audit history. Follow-up date, reason and responsible party are available to authorized staff; tenants can see the date and reason but not staff identity.

## Deliberate limits

The product has no vendor settlement, payment, supplier catalog, inventory, asset registry, calendar or reminder subsystem. `NEEDS_FOLLOW_UP` cannot be verified closed; staff must reject it for further work, schedule follow-up if appropriate, and verify a later completion. Tenant feedback is a shared comment and does not independently reopen a verified repair.

## Job materials and recorded costs (Batch B)

Purchases are job-specific records tied to a line on the current approved, itemized quotation. A purchase snapshots the material description and unit and retains its quotation and line references. Cumulative purchase quantity cannot exceed the approved material quantity. A changed estimate must be resubmitted and approved before it can authorize further purchases. Purchase creation is idempotent per organization key; reusing a key with different details is rejected.

Only an organization owner or property manager can record a purchase. If its calculated material cost exceeds the approved material subtotal, an owner or property manager must provide an explicit reason; HODI sets no monetary ceiling. This records the authorized variance and does not change the approved quotation. Assigned technicians can see material descriptions and received quantities for completion linkage, but not supplier or price data. They cannot record purchases or acknowledge deliveries. Owners, property managers and caretakers can acknowledge delivered quantities, except a purchase creator cannot acknowledge their own purchase.

Purchase state (`RECORDED`, `PARTIALLY_RECEIVED`, `RECEIVED`) describes recorded order and acknowledged delivery only. Receipt requires an evidence reference and actor; the reference is not independently verified. The current media configuration stores files locally, so this workflow intentionally stores references and does not accept evidence uploads. Production deployment still needs a durable, access-controlled evidence-storage policy. A receipt, purchase record or supplier reference does not prove supplier payment. HODI does not record supplier invoices or supplier settlements.

Completion material-use entries may link to a received purchase. The service uses the purchase's snapshotted description, unit and unit price and prevents cumulative consumption above acknowledged receipts. Completion material cost is reported separately from purchases and excluded from recorded job cost to avoid counting the same material twice. Recorded job cost is purchase totals + completion labour + completion other costs; variance compares it with the approved quotation total. It is provisional until a current approved quotation, verified completion and reconciled linked material-use costs exist. Legacy unlinked material-use entries remain visible but make material reconciliation provisional. A purchase overrun or completion overrun requires explicit owner/property-manager reason; neither changes the quote. No supplier payment or rental/subscription ledger entry is created.

No configurable approval ceiling or emergency-spending policy has been added. The existing safety override remains unchanged; it does not authorize a quotation amount or remove the explicit cost-overrun reason and role checks.

## Completion evidence and turnover readiness (Batch C)

`RepairCompletion` remains the single completion and verification record. The assigned technician submits completion; an authorized property owner, manager or caretaker can verify or reject it, with the existing self-approval restriction, decision actor/time and rejection notes. A decided completion is not changed to represent a later attempt: follow-up work is recorded as a new completion through the existing lifecycle.

Completion evidence is currently metadata-only. `RepairCompletionEvidence` links a categorized private evidence reference and caption to both a completion and its maintenance request, and records the actor and timestamp. The completion submitter may add evidence while that completion is submitted. Authorized organization maintenance readers and the current assigned technician may read it; tenants cannot read this private evidence endpoint. Records are immutable and there is no removal API. Evidence references are identifiers only: HODI does not accept file uploads, issue public URLs, or treat a reference as proof that the work is correct. The configured media storage is local filesystem storage, with no verified durable, access-controlled production provider. Production photo/document upload requires a separate durable private-storage integration and access policy.

`TurnoverAssessment` is separate from ordinary repair verification and from the unit's occupancy status. An authorized owner, manager or caretaker may request an inspection for a vacant unit and record a structured checklist, outstanding issues and a failed/not-ready result. Only an owner or manager may record READY. A READY decision requires the unit to remain vacant, all checklist items to pass, no outstanding issues, and the linked repair job to be closed with a verified latest completion. Reassessment creates a linked immutable history record. A unit with an active lease or incompatible status cannot be marked ready. The workflow never changes `Unit.Status`, lease history or financial records; unit availability remains governed by existing property and lease lifecycle services. A verified ordinary repair does not create a turnover assessment or make a unit available.

The readiness history is private to organization maintenance staff; tenants and technicians do not receive landlord inspection details through this endpoint. Caretakers may report inspection failures but cannot confirm readiness. No standard checklist template, mandatory inspection schedule, or additional authority for caretaker readiness decisions has been defined; those policies remain product decisions.
