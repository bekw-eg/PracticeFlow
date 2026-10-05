# Disciplines, topics and teaching materials

The Teacher workspace provides a curriculum domain alongside groups,
internships, reports, templates, the legacy editor, document checks, review
groups and presentation exports. It creates no assignment, analysis job,
generated test, grading record or AI request.

## Existing architecture reused

- [RequestContext](../backend/app/dependencies/auth.py) revalidates active
  membership and role on every request.
- [GroupRepository](../backend/app/repositories/group_repository.py) supplies
  existing assigned student cohorts. Review groups remain a separate domain.
- [StorageService](../backend/app/storage/base.py) and its Local/S3 backends
  persist private objects with exclusive creation.
- [DOCX preflight](../backend/app/services/docx_preflight.py) supplies bounded
  ZIP/XML security checks; the DOCX default policy stays unchanged.
- [ResourceGuard](../backend/app/resource_protection.py) enforces upload rate,
  user quota and the combined organization storage budget.
- React Query, Axios, shared state/pagination views, existing input/button
  styles, toast and ru/kk/en i18next resources serve the new UI.

## Data and authorization

The additive migration is
[6e7f8091a2b3](../backend/alembic/versions/6e7f8091a2b3_disciplines_topics_materials.py).
It follows the group presentation migration and does not alter legacy tables.

Discipline stores organization, creator user, name, description, optional
academic year and archive state. Its creator references a membership in the
same organization. Only the exact Teacher owner can read or change it.
Students, Directors and Super Admins receive 403, matching existing direct
Teacher workflow conventions. Inaccessible tenant/owner IDs return 404.
No request payload accepts organization or owner identity.

DisciplineGroup links the existing Group through tenant-aware composite foreign
keys. Creation/replacement requires each group to be assigned to the Teacher
in the active organization. A subsequently unassigned group is omitted from
the visible linked-group list. Group and internship semantics do not change.

DisciplineTopic carries organization and discipline, title, description,
learning goal, nonnegative position and archive state. Default positions are
allocated while locking the discipline; ordering is position then UUID for
stable pagination. Explicit positions need not be unique.

TeachingMaterial stores private original file metadata, original-byte SHA-256,
uploader, parent discipline/topic, upload request key and deletion timestamps.
A composite foreign key binds its organization, discipline and topic together.
Public schemas omit storage keys, tenant/owner IDs and upload keys.

DELETE discipline/topic archives it. Archived content remains readable and
downloadable; topic edits and new uploads require active parent/content.
PATCH with is_archived=false restores the object. Archive retains files.

## API and frontend

All paths are under /api/v1:

| Resource | Operations |
| --- | --- |
| /disciplines | GET paginated own list, POST create |
| /disciplines/{id} | GET, PATCH metadata/group IDs/archive, DELETE archive |
| /disciplines/{id}/groups | GET currently accessible linked groups |
| /disciplines/{id}/topics | GET paginated topics, POST create |
| /topics/{id} | GET, PATCH metadata/position/archive, DELETE archive |
| /topics/{id}/materials | GET paginated metadata, POST multipart upload |
| /materials/{id} | GET metadata, DELETE material/file |
| /materials/{id}/download | GET authorized attachment |

Discipline/topic collection GETs accept archived=true to list archived rows.
Collections use existing offset/limit parameters and pagination headers.

Teacher navigation exposes /disciplines, /disciplines/:disciplineId and
/disciplines/:disciplineId/topics/:topicId. Query keys include current
organization and user so switching organization cannot reuse another context's
cached curriculum. Mutations invalidate corresponding server queries.
A topic URL is checked against its returned discipline before showing materials.

## Upload and deletion

Materials accept PDF, DOCX and PPTX up to 20 MiB. The complete multipart body
is bounded to that limit plus 64 KiB before spooling, including chunked uploads.
The supplied 21 MiB Nginx request ceiling accommodates this limit.
Extension and declared MIME must agree; generic browser MIME is allowed only
alongside independent byte checks. Office files pass existing ZIP/XML limits,
path, corruption, encryption and macro checks with the correct main
part/type/root. PDF identification checks the header and end marker. It is not
malware scanning or full PDF structural validation.
No material is rendered, executed, extracted or analyzed.

The service stages bounded chunks, hashes original bytes and builds an
organization/discipline/topic/material UUID key. Storage uses save_new; file
names cannot choose keys. DB failure removes a newly saved file only after a
separate read proves it is orphaned. If commit outcome cannot be verified,
the object is retained for operational reconciliation.

Multipart POST requires Idempotency-Key. Identical topic/owner/key/filename/
title/size/hash retries return the original row; conflicting or deleted retries
return 409. The UI preserves the key after an uncertain response.

Downloads recheck membership, Teacher role, organization, uploader/discipline
owner and deletion state. Attachments stream through authenticated API with
private no-store caching and safe encoded filenames; no public S3 URL exists.

Deletion commits a tombstone before removing the private object. GET/list/
download immediately hide the row. Failed storage removal returns 503 with
MATERIAL_DELETE_PENDING; repeated DELETE retries the same file without reopening
access. Until confirmed removal, bytes still count toward organization quota.
Metadata/tombstones remain in PostgreSQL; there is no automatic curriculum
retention cleanup. The UI retains a retry action after the row leaves its list.

Existing FILE_GENERATED, FILE_DOWNLOADED and FILE_DELETED audit events use
entity_type=teaching_material and bounded size metadata. Names, goals, document
text and object keys do not enter audit payloads.

The copy-only LocalStorage-to-S3 tool includes active teaching materials.
Run its existing dry-run/copy/checksum workflow before switching storage.
Reconcile tombstoned files in the original backend first.

## Rollout, rollback and remaining boundaries

Apply alembic upgrade head before deploying this API/UI. Back up PostgreSQL
metadata and private objects together. Application rollback should keep the
additive tables; migration downgrade destroys curriculum metadata and requires
separate private-object reconciliation. It does not change legacy tables.

Storage outages and lost DB/S3 acknowledgements can leave retained orphans or
pending tombstones. There is no distributed transaction or automatic orphan
reconciler. Operators must establish DB outcome and ownership before removing
an object. Pending tombstones can be retried via the owner-authorized API.

This module currently depends on the document-check/group-presentation baseline
in PR #29. Its migration parent and shared preflight/storage interfaces require
that baseline before merge/deployment.

Future assignments, criteria, check groups, evaluation and lesson preparation
can reference this curriculum without repurposing Group or DOCX submissions.
