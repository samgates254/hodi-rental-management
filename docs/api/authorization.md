# API Authorization

All role grants apply only to active memberships in the specific active organization. Read access covers `GET`, `HEAD`, and `OPTIONS`; write access covers `POST`, `PUT`, `PATCH`, and `DELETE`.

| Role | Properties | Leases | Billing | Maintenance | Tenants |
| --- | --- | --- | --- | --- | --- |
| `OWNER` | Read/write | Read/write | Read/write | Read/write | Read/write |
| `PROPERTY_MANAGER` | Read/write | Read/write | Read | Read/write | Read/write |
| `ACCOUNTANT` | Read | Read | Read/write | No access | Read |
| `CARETAKER` | Read | No access | No access | Read/write | Read |
| `TECHNICIAN` | No access | No access | No access | Assigned work only | No access |
| `SUPPORT` | No access | No access | No access | No access | No access |

Organization creation is available to authenticated users, who become the new organization owner. Only active owners can manage organization memberships or update/delete the organization. An organization must retain at least one active owner.

Property, lease, tenant, billing, and maintenance endpoints enforce this matrix. Technician maintenance access is object-scoped to assigned work orders and does not grant organization-wide maintenance rights. Tenant accounts are not memberships; a linked tenant may read their own tenant row, invoices, and payments, and may report maintenance for an active lease.
