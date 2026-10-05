# Role and tenant-boundary matrix

Roles are evaluated from the active validated organization membership. UI
visibility never substitutes for server-side authorization. A user with more
than one membership receives context from the validated current membership; a
client cannot supply another `organization_id` to redirect tenant-scoped work.

| Capability | Super Admin | Director | Teacher | Student |
| --- | --- | --- | --- | --- |
| Disciplines, topics and teaching materials | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Own curriculum in the active organization; link assigned existing groups; authorized private file download/deletion | No access |
| MFA required | Yes | Yes | No by current policy | No by current policy |
| View/manage organization members | Yes, within current organization; global organization management endpoints are Super Admin-only | View/manage permitted Teacher/Student members in current organization | No | No |
| Change/invite/reset privileged membership | Yes | No — cannot change, deactivate, invite or reset Director/Super Admin | No | No |
| Groups, departments, specialties and assignment | Yes, current organization | Yes, current organization | Manage membership in assigned groups | No |
| Templates/internships/review workflow | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Create/manage authorized templates and internships; review assigned-group reports | No |
| Report document | No direct Teacher/Student report endpoint | No direct Teacher/Student report endpoint | Read/review reports only for assigned groups | Read/save/submit own report only |
| Comments | No direct Teacher/Student comment endpoint | No direct Teacher/Student comment endpoint | Create/resolve teaching comments in authorized report | Create/read permitted comments on own authorized report |
| File upload/download | No direct Teacher/Student file endpoint | No direct Teacher/Student file endpoint | Authorized report/workflow only | Own authorized report/workflow only |
| Export jobs/artifacts | No direct Teacher/Student export endpoint | No direct Teacher/Student export endpoint | Authorized report/workflow only | Own authorized report/workflow only |
| Audit events and integrity verification | Yes, **current organization only** | No | No | No |
| MFA peer recovery approval | Yes, for another Super Admin in same organization | No | No | No |

## Important boundaries

- A Super Admin does not obtain a tenant selector for audit events: audit list
  and integrity verification remain scoped to the active organization.
- Teacher report access requires the server-validated assigned group; a Teacher
  does not gain access merely by knowing a report ID.
- Student updates require ownership and optimistic `expected_revision`; a stale
  request does not overwrite a newer document.
- File and export download recheck current access to the source report, so a
  completed artifact is not a permanent RBAC bypass after membership/group
  changes.
- MFA protects privileged memberships, not a broad organization-wide role
  switch. Session/challenge state is invalidated as part of relevant security
  changes.

This matrix is an operational overview. Endpoint-level policy and tests remain
authoritative; update this document whenever a role, route or tenant-boundary
rule changes.
