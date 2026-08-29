# Архитектура PracticeFlow

PracticeFlow — multi-tenant приложение для учебной практики. Этот документ
описывает текущую архитектуру repository и её security boundaries; он не
описывает будущий HA-кластер или managed cloud-инфраструктуру.

## Компоненты

| Компонент | Роль | Persistent data / boundary |
| --- | --- | --- |
| Frontend | React UI, собранный Vite и раздаваемый внутренним Nginx | Не является источником tenant/role truth; получает только API responses |
| Caddy | Единственная public TLS edge: redirect HTTPS, HSTS, proxy и CIDR gate для `/metrics` | Certificate/account data находятся в Caddy volume; config и domain задаёт deployer |
| Backend | FastAPI API, RBAC, tenant enforcement, document workflow, validation и observability | Работает с PostgreSQL, Redis и private S3 через private network |
| PostgreSQL | Authoritative state: organizations, memberships, documents, reports, export jobs и audit trail | Persistent source of truth; не публикуется наружу |
| Redis | Login/MFA throttling, resource guards, export queue, leases и worker heartbeat | Derived/short-lived security and work state; `noeviction`, failures are fail-closed |
| Export worker | Отдельный consumer durable export jobs; renderer запускается в killable child process | PostgreSQL claim/lease определяет правду, Redis только transport/guard |
| S3-compatible storage | Private images и finished export artifacts | Objects доступны только через authorized backend, не public URL |
| Prometheus | Внешний monitoring system, scrape безопасных aggregate metrics | Repository не deploys Prometheus; Caddy пропускает scrape только from `METRICS_ALLOWED_CIDR` |
| Sentry | Optional external error tracking | Получает только sanitized event; request/user/context, breadcrumbs, exception text and stack trace удаляются до send |

```text
Browser (untrusted)
  -> Caddy public TLS boundary
  -> frontend Nginx private proxy
  -> FastAPI backend private application boundary
       -> PostgreSQL (authoritative state)
       -> Redis (guards, queue, heartbeat)
       -> private S3-compatible storage

export-worker -> PostgreSQL + Redis + private S3
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

## Document autosave and review flow

1. A Student reads their own report document through backend authorization.
2. The frontend sends a save with `expected_revision`; backend atomically
   updates the document and revision in PostgreSQL.
3. A stale editor receives the documented conflict response rather than
   overwriting newer content. The UI reloads/reconciles the latest server
   document.
4. Teacher reads only reports for groups assigned to that teacher and has a
   resolved, read-only document view; review/comment actions are separately
   role checked.

Document contents live in PostgreSQL. Request logs and Prometheus labels use
route templates and safe operation fields, not document text or filenames.

## Export and storage flow

```text
authorized API request
  -> PostgreSQL export_jobs row (durable, deduplicated for active format)
  -> Redis queue notification
  -> export-worker claims PostgreSQL lease
  -> isolated renderer child
  -> private S3 object
  -> PostgreSQL terminal status
  -> authorized API download checks current tenant and role again
```

Redis queue messages may be duplicated or lost during an outage; this is safe
because the PostgreSQL job and lease state are authoritative. On restart, a
worker requeues queued and expired-lease jobs. The worker rechecks membership,
role and current report access before rendering. Timeout/cancel terminates the
child before the job becomes terminal and releases its Redis concurrency slot.

Uploads are staged and validated as allowed image bytes before private storage.
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
