# HODI Platform Roadmap

This roadmap sequences the platform around a reliable rental and operating core. Later milestones are gated by evidence from earlier workflows; this document does not authorize building them in advance.

| Milestone | Scope | Gate |
| --- | --- | --- |
| M2 | Operational and financial integrity: invoice idempotency, lease occupancy protection, verified payment outcomes, tenant API contracts, and a coherent maintenance identity. | Reconciliation and authorization tests pass; production database concurrency behavior is verified. |
| M3 | **Implemented foundation:** unified maintenance and repair outcomes: triage, eligible assignment, request-scoped quotations/approval, completion verification, actual costs, materials used, and structured failure/outcome data. | Continue hardening PostgreSQL concurrency, technician response handling, cancellation policy, and production role workflows before broad rollout. See [maintenance workflow](./maintenance-workflow.md). |
| M4 | Parts catalog, supplier procurement, and asset lifecycle. | Repeated repair demand and part usage show a justified catalog/procurement workflow. |
| M5 | One validated household marketplace transaction. | Catalog/order ownership, payment settlement, refunds, and fulfillment responsibilities are defined. |
| M6 | Utility and transaction integrations. | Provider contracts, authorization, reconciliation, and tenant data controls are reviewed. |
| M7 | Logistics and demand optimization. | Reliable order/stock/delivery events exist and measurable delivery constraints are available. |
| M8 | Industrial intelligence, manufacturing, and circular supply chains. | Sufficient quality history, validated baselines, and economic evidence justify forecasting, optimization, or manufacturing workflows. |

Keep the application a modular monolith while its operational boundaries remain manageable. Add background delivery mechanisms only when a demonstrated workflow needs retryable post-commit work.
