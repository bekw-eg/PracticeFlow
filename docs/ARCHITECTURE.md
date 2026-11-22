# Архитектура PracticeFlow

The additive [curriculum module](DISCIPLINES.md) uses the same validated
membership context, Teacher ownership, private storage and resource quotas.
Disciplines, topics and teaching materials remain independent of direct document checks.

PracticeFlow — multi-tenant приложение для преподавательской проверки документов (DOCX) и локального анализа схожести. Этот документ
описывает текущую архитектуру repository и её security boundaries; он не
описывает будущий HA-кластер или managed cloud-инфраструктуру.

## Компоненты

| Компонент | Роль | Persistent data / boundary |
| --- | --- | --- |
| Frontend | React UI, собранный Vite и раздаваемый внутренним Nginx | Не является источником tenant/role truth; получает только API responses |
| Caddy | Единственная public TLS edge: redirect HTTPS, HSTS, proxy и CIDR gate для `/metrics` | Certificate/account data находятся в Caddy volume; config и domain задаёт deployer |
| Backend | FastAPI API, RBAC, tenant enforcement, document-check workflow, validation и observability | Работает с PostgreSQL, Redis и private S3 через private network |
| PostgreSQL | Authoritative state: organizations, memberships, groups, disciplines, check profiles, submissions, check jobs, review groups и audit trail | Persistent source of truth; не публикуется наружу |
| Redis | Login/MFA throttling и resource guards | Derived/short-lived security and work state; `noeviction`, failures are fail-closed |
| Document-check worker | Отдельный consumer очереди DOCX-проверок; анализатор запускается в ограниченном дочернем процессе | PostgreSQL хранит очередь, lease, попытки, итог и неизменяемые замечания |
| S3-compatible storage | Private immutable DOCX originals, teaching materials и презентации проверок групп | Objects доступны только через authorized backend, не public URL |
| Prometheus | Внешний monitoring system, scrape безопасных aggregate metrics | Repository не deploys Prometheus; Caddy пропускает scrape только from `METRICS_ALLOWED_CIDR` |
| Sentry | Optional external error tracking | Получает только sanitized event; request/user/context, breadcrumbs, exception text and stack trace удаляются до send |

```text
Browser (untrusted)
  -> Caddy public TLS boundary
  -> frontend Nginx private proxy
  -> FastAPI backend private application boundary
       -> PostgreSQL (authoritative state)
       -> Redis (throttling, resource guards)
       -> private S3-compatible storage

document-check-worker -> PostgreSQL + private S3
Prometheus allowed CIDR -> Caddy -> /metrics
```

## Границы доверия и data flow

1. Browser и internet недоверенны. Caddy terminates TLS and overwrites
   client-supplied forwarding headers; backend trusts forwarding data only from
   configured proxy hops.
2. Frontend never chooses an `organization_id` for a tenant-scoped operation.
   Backend derives the active organization and role from validated membership.
3. PostgreSQL, Redis, backend and frontend ports stay private. Caddy is the
   only public service in the supplied production template.
4. S3 credentials belong only to backend/worker and are restricted to a
   dedicated private bucket/prefix. Browser uploads/downloads pass through
   authorization checks rather than receiving public object URLs.
5. Prometheus and Sentry are external trust boundaries. Metrics expose fixed,
   low-cardinality labels; Sentry is optional and event data is scrubbed before
   it leaves the process.

## Authentication, MFA and tenant isolation

```text
Browser -> /auth/login -> backend -> PostgreSQL membership/password state
                           -> Redis login limiter
  privileged role? -> short-lived HttpOnly MFA challenge -> TOTP/recovery flow
  success -> access token in browser memory + refresh cookie
  each request -> validated token + active membership -> tenant context
```

Director and Super Admin require MFA. A successful password check for a
privileged membership produces a short-lived challenge, not an API session.
TOTP enrollment, TOTP verification and recovery-code use complete the
challenge. Super Admin peer recovery and two-custodian break-glass create only
a new enrollment opportunity; they do not bypass the MFA policy.

Every tenant-scoped repository/service call receives the server-derived
organization context. The client has no organization selector to redirect an
operation. A missing or inaccessible object normally remains indistinguishable
from a non-existent object (`404`) to avoid cross-tenant disclosure.

## Document-check domain (teacher-only direct checking)

PracticeFlow provides a Teacher-only document checking and similarity analysis domain.

```text
CheckProfile
  -> CheckProfileVersion (DRAFT -> PUBLISHED -> RETIRED)
       -> ordered, typed CheckRule configuration
```

Every row in this domain carries `organization_id`. Composite foreign keys
bind profile versions, rules, and teacher submissions to the same
tenant as their parent. Services apply
the same tenant checks using the organization, teacher, and
role derived from `RequestContext`; request payloads never choose a tenant.

Published profile versions and their rules are immutable.

Phase 1 stores typed rule configuration. Phase 2.1 added immutable DOCX
submission and a durable job record. Phase 2.2 executes page format/margins,
font/size, and paragraph spacing/indent rules. The current product entry point
is a direct Teacher upload: a student account, group, roster, and assignment are
not required. Other configured rule types are counted as skipped. Spelling,
annotations, automatic grading, and teacher grading are not implemented.

### Current immutable Teacher upload pipeline

```text
Teacher + active organization -> exact PUBLISHED CheckProfileVersion
  -> TeacherDocumentSubmission (append-only, optional student/work label)
       -> private original DOCX object (unchanged bytes + SHA-256)
       -> exactly one DocumentCheckJob (QUEUED)
       -> immutable structured findings
```

The server derives both `organization_id` and `teacher_id` from the validated
request context. History, original downloads, and findings require the same
active tenant and exact Teacher owner; inaccessible IDs return `404`. Uploads
are multipart requests with an `Idempotency-Key`. An identical retry returns
the existing submission and job, while a conflicting reuse returns `409`.
Each accepted upload pins an exact PUBLISHED profile version. Direct checks do
not depend on later profile drafts, group membership, or student records.

The backend stages bounded chunks in a temporary file, computes SHA-256 over
the original bytes, and validates the ZIP/OOXML package without rewriting it.
It rejects `.docm`, OLE/encrypted Office containers, encrypted ZIP entries,
macro payloads/content types, invalid paths, corrupt packages, and missing
required OOXML parts. Configurable limits bound upload bytes, entry count,
individual/total expanded bytes, and compression ratio. Settings are
`DOCX_MAX_UPLOAD_BYTES`, `DOCX_MAX_ZIP_ENTRIES`,
`DOCX_MAX_UNCOMPRESSED_BYTES`, `DOCX_MAX_ENTRY_BYTES`, and
`DOCX_MAX_COMPRESSION_RATIO`. Existing resource guards also apply request
limits, user upload quotas, and combined tenant storage quotas.
The backend also bounds the complete HTTP multipart envelope before spooling
(DOCX limit plus 64 KiB framing), including requests without Content-Length.
Partially spooled files are closed when this envelope limit is crossed.
The supplied nginx proxy permits 21 MiB; keep its ceiling above a custom
`DOCX_MAX_UPLOAD_BYTES` plus framing when changing deployment settings.

Originals use exclusive creation through the common private storage
abstraction: the server constructs a unique key containing tenant, source
owner (Teacher or assignment/Student), submission, and SHA-256. An existing key cannot be
overwritten. Database failures remove only the newly created orphan object;
storage failures do not create submission or job rows. Temporary staging files
close on every outcome. The new domain does not reuse the legacy editor's
`File` metadata or export worker.
For a lost S3 PUT acknowledgement, a per-write ownership marker and conditional
delete permit cleanup only of that operation's new object. If database commit
confirmation is lost, a separate read must prove the original is orphaned before
deletion. If either dependency remains unreachable, cleanup cannot be proven;
the object is conservatively retained instead of risking deletion of an accepted
original. Crash/dependency-outage orphan reconciliation remains operational work
for a subsequent stage; no distributed transaction is claimed.

The current API exposes these Teacher-only routes below
`/api/v1/document-checks`:

- `GET/POST /teacher/submissions`; POST is a multipart DOCX upload with an
  exact published `profile_version_id`, optional `student_label`, and required
  `Idempotency-Key`;
- `GET /teacher/submissions/{submission_id}`;
- `GET /teacher/submissions/{submission_id}/original`;
- `GET /teacher/submissions/{submission_id}/findings` with bounded pagination.

Collections use bounded pagination and the existing pagination headers.
Downloads recheck active tenant, role, and ownership on every request; another
tenant's object returns `404`. Responses never disclose storage keys or public
S3 URLs. Normalized filenames produce safe attachment headers. Upload,
Teacher download, job creation, and malicious-file rejection are
audited without document text, binary payloads, full storage keys, or internal
exception details.

The Teacher-only UI provides direct DOCX upload, an optional student/work label,
job status, history, rule coverage, paginated structural findings, and
authorized original download. Unsupported rules and truncated result sets are
shown explicitly. Student navigation and routes do not expose document checks.
Original content remains read-only; there is no new document editor.
`accept=".docx"` is only a browser hint; server checks determine acceptance.
The workflow follows the feature flag returned by `/auth/me`. While a direct
job is queued or processing, the UI polls its history until the result arrives.

`DocumentCheckJob` supports QUEUED, PROCESSING, COMPLETED, and FAILED with
timestamps, bounded attempts, worker lease, analyzer version, safe error
fields, and a structured result summary. The independent worker claims jobs
with PostgreSQL `FOR UPDATE SKIP LOCKED`, verifies stored size and SHA-256,
copies the original into a private temporary directory, and runs OOXML
analysis in a spawned process with a hard timeout. Expired leases are requeued
or fail after the configured attempt limit. A job becomes COMPLETED only after
its findings are inserted in the same transaction.

Findings contain the rule ID/type, category, severity, fixed code, structural
location, and expected/actual values. They never contain paragraph text,
filenames, storage keys, or internal exceptions. Database triggers make
terminal jobs and findings immutable. Analyzer start/completion/failure are
audited with bounded operational metadata. `DOCUMENT_CHECK_MAX_FINDINGS` caps
database growth and the result summary records truncation. Automatic grading,
teacher grading, and annotated DOCX/PDF are absent.

### Feature flags and storage flow

The document-check domain is controlled by deployment settings. `DOCUMENT_CHECK_ENABLED` hides the document-check API and UI when disabled (defaults to `true`).

Storage keys are server-generated under organization UUID prefixes and never
come from a client filename. S3 unavailability returns a controlled `503`; the
application does not fall back to public or local production storage.

## Audit trail

Audit events are stored in PostgreSQL with tenant, sequence, predecessor hash
and hash of canonical immutable payload. Safe HMAC fingerprints replace raw
request/correlation/IP values. Super Admin may view and verify the current
organization's audit chain; those access actions are themselves audited.

This is an application integrity aid, not independent WORM evidence. A party
with privileged database or deployment access can still alter the underlying
storage. Retention anchors keep the remaining chain verifiable after cleanup,
but they do not provide external immutability. See
[data retention](DATA_RETENTION.md) for the operational limitation.
