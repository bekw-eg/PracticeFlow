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
| Director academic-process dashboard | No dedicated dashboard endpoint | Read-only aggregates and safe operational lists for the current organization (groups, students, teachers) | No | No |
| Check profiles and versions (Phase 1) | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Create/manage profiles; edit only DRAFT rules; publish and retire versions | No |
| Original DOCX submission | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Upload a ready DOCX directly, label it, list own uploads, and download the immutable original | No access |
| Document-check results & review groups | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Read job summary, findings, similarity matches, review groups and PPTX presentations only for own direct uploads in the active organization | No access |
| Student web workspace | N/A | N/A | N/A | Notice screen stating the web workspace is for teachers and administration, with sign-out |
| Audit events and integrity verification | Yes, **current organization only** | No | No | No |
| MFA peer recovery approval | Yes, for another Super Admin in same organization | No | No | No |

## Important boundaries

- A Super Admin does not obtain a tenant selector for audit events: audit list
  and integrity verification remain scoped to the active organization.
- Check-profile configuration, direct DOCX upload, history, original download,
  and findings APIs are Teacher-only. Active tenant and teacher identity come
  from `RequestContext`; no profile or submission payload chooses
  `organization_id` or `teacher_id`.
- A Teacher cannot assign an unpublished/retired profile version or operate on
  a group that is not currently assigned to that Teacher. Students cannot
  mutate profiles, versions, rules, or assignments.
- A direct upload pins an exact PUBLISHED profile version. It does not require
  a student account, roster snapshot, group, assignment, or deadline.
- Direct DOCX submissions are immutable and append-only. The Teacher cannot
  edit, replace, or delete an accepted original or its metadata. An identical
  retry with the same `Idempotency-Key` returns the accepted submission and its
  existing job; a conflicting reuse returns `409`.
- Original download rechecks active tenant and exact Teacher ownership.
  Cross-tenant, another Teacher's, and inaccessible objects return `404`.
  Filenames are normalized, storage stays private, and API responses never
  expose original storage keys or public S3 links.
- Jobs are created in QUEUED and claimed only by the independent analyzer
  worker. Phase 2.2 checks page format/margins, fonts/sizes, and paragraph
  spacing/indents. Unsupported rules are explicitly counted as skipped.
  Results follow the same active-tenant and exact-Teacher ownership as original
  downloads. There is no automatic grading, teacher grading,
  annotated DOCX/PDF, or document editor.
- Student-submission and check-assignment routes and tables have been removed.
- Director dashboard data is derived from the active organization in the
  validated request context. It exposes organization, group, student and teacher
  summary counts and operational metadata only.
- MFA protects privileged memberships, not a broad organization-wide role
  switch. Session/challenge state is invalidated as part of relevant security
  changes.

This matrix is an operational overview. Endpoint-level policy and tests remain
authoritative; update this document whenever a role, route or tenant-boundary
rule changes.
