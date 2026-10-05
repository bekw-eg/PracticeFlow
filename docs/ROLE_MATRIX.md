# Role and tenant-boundary matrix

Roles are evaluated from the active validated organization membership. UI
visibility never substitutes for server-side authorization. A user with more
than one membership receives context from the validated current membership; a
client cannot supply another `organization_id` to redirect tenant-scoped work.

| Capability | Super Admin | Director | Teacher | Student |
| --- | --- | --- | --- | --- |
| MFA required | Yes | Yes | No by current policy | No by current policy |
| View/manage organization members | Yes, within current organization; global organization management endpoints are Super Admin-only | View/manage permitted Teacher/Student members in current organization | No | No |
| Change/invite/reset privileged membership | Yes | No — cannot change, deactivate, invite or reset Director/Super Admin | No | No |
| Groups, departments, specialties and assignment | Yes, current organization | Yes, current organization | Manage membership in assigned groups | No |
| Director academic-process dashboard | No dedicated dashboard endpoint | Read-only aggregates and safe operational lists for the current organization; no report content, comments, or review actions | No | No |
| Templates/internships/review workflow | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Create/manage authorized templates and internships; review assigned-group reports | No |
| Check profiles and versions (Phase 1) | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Create/manage profiles; edit only DRAFT rules; publish and retire versions | No |
| Document-check assignments | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Optional profile/roster administration inside an assigned group; direct checking does not require an assignment | No access in the current product flow |
| Original DOCX submission | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Upload a ready DOCX directly, label it, list own uploads, and download the immutable original | No access |
| Document-check results | No direct Teacher workflow endpoint | No direct Teacher workflow endpoint | Read job summary and findings only for own direct uploads in the active organization | No access |
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
  annotated DOCX/PDF, or new document editor. Legacy editor, templates,
  reports, comments, and export worker remain available under their existing
  controls; `LEGACY_DOCUMENT_EDITOR_ENABLED` stays enabled by default.
- Historical student-submission routes and tables remain for additive migration
  compatibility, but they are absent from the UI/OpenAPI and return `404` while
  `DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED=false`, which is the default.
- Director dashboard data is derived from the active organization in the
  validated request context. It exposes status counts and operational metadata
  only, never report documents, versions, comments, or review actions.
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
