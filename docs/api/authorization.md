# API Authorization

All role grants apply only to active memberships in the specific active organization. Read access covers `GET`, `HEAD`, and `OPTIONS`; write access covers `POST`, `PUT`, `PATCH`, and `DELETE`.

| Role | Properties | Leases | Billing | Maintenance |
| --- | --- | --- | --- | --- |
| `OWNER` | Read/write | Read/write | Read/write | Read/write |
| `PROPERTY_MANAGER` | Read/write | Read/write | Read | Read/write |
| `ACCOUNTANT` | Read | Read | Read/write | No access |
| `CARETAKER` | Read | No access | No access | Read/write |
| `TECHNICIAN` | No access | No access | No access | No access until work can be scoped to assigned tickets |
| `SUPPORT` | No access | No access | No access | No access |

Organization creation is available to authenticated users, who become the new organization owner. Only active owners can manage organization memberships or update/delete the organization. An organization must retain at least one active owner.

Property and lease endpoints enforce the matrix today. Billing and maintenance have no API views yet; their role grants are policy only and do not imply those endpoints are implemented. When maintenance endpoints are added, technician access must be restricted to assigned work orders before granting the technician role.