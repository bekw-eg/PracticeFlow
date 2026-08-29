# PracticeFlow observability runbook

The supplied metrics deliberately use only low-cardinality labels: HTTP method,
route template, status/status class; dependency component/result; storage
backend/operation/result; MFA action/result; export format/status; and a fixed
limit-block reason. They never contain emails, users, organizations, tokens,
filenames, object keys, document contents, raw URLs or exception text.

Configure Prometheus to scrape `https://<domain>/metrics` from the exact
`METRICS_ALLOWED_CIDR`. Caddy keeps the existing ACL and returns `403` to other
sources. Import `practiceflow-dashboard.json` into Grafana and load
`prometheus-alerts.yml` through the deployment's normal Prometheus rule path.
Neither file deploys Prometheus/Grafana or opens a port.

## High HTTP 5xx rate

Check dashboard status class and latency, then inspect structured backend logs
by `request_id`. Logs retain route template, status and exception type only;
use the request ID in the authorized application/audit trail if deeper access
is required. Confirm PostgreSQL/Redis/S3 metrics before rollback.

## High HTTP p95 latency

Compare request duration with database pool `checked_out`, dependency state and
export queue depth. Do not add raw query or document-data logging to diagnose
this; collect a short, access-controlled profiler sample if required.

## Dependency unavailable

For PostgreSQL, Redis or S3, verify the internal Compose service health,
network/DNS/TLS credentials, provider status and the least-privilege secret
mount. Redis failures are fail-closed for rate/resource protection; S3 failures
keep private files unavailable rather than attempting a local fallback.

## Export queue backlog

Check `practiceflow_export_worker_active`, heartbeat age, terminal transition
rate and worker CPU/RAM. A backlog with fresh workers usually indicates document
rendering capacity; scale workers only after reviewing the per-organization
concurrency values and resource limits.

## Database pool near exhaustion

First check PostgreSQL availability, latency and the configured connection
budget; do not increase `max_overflow` as an immediate response. A saturated
pool makes API requests wait and can consume the PostgreSQL reserve needed by
migrations and recovery. Check for long transactions, then scale CPU/RAM or
reduce concurrent work. Any pool or replica change must satisfy the formula in
[`docs/CAPACITY_PLANNING.md`](../../docs/CAPACITY_PLANNING.md).

## Redis memory near limit

Redis is deliberately configured with `maxmemory-policy noeviction` because it
holds login, resource-guard and export-queue state. When it reaches its limit,
those operations fail closed with a controlled `503`; do not change the policy
to an eviction mode. Identify unexpected key growth and TTL regressions, then
raise the explicit Redis limit and container reservation only after confirming
host headroom. A Redis restart is an incident decision: it clears security
state and must be followed by login/resource/export checks.

## Storage error rate

Compare storage failures with the S3 dependency gauge, TLS/DNS status and the
least-privilege bucket credential. Keep uploads and downloads unavailable on a
storage error rather than enabling a local fallback. Do not place endpoint
URLs, bucket names, object keys or credential values in Prometheus labels or
incident-chat excerpts.

## Worker heartbeat stale

Check the `export-worker` container and its `--check` healthcheck, then Redis.
The heartbeat is stored as a short TTL Redis sorted set and is refreshed during
polling and every 15 seconds while a renderer child runs. Restart the worker if
it is wedged; its stale leases are requeued safely by the next worker.

## Export failures or timeouts

Inspect status transitions and `practiceflow_export_job_duration_seconds`, then
review structured worker logs using the safe `export_job_id` correlation field.
Confirm that child renderer timeout and slot release occurred. Do not raise the
hard timeout blindly: reproduce the authorized document in a non-production
environment and establish CPU/RAM limits first.

## Resource-limit spike

Break down `practiceflow_limit_blocks_total` by fixed `reason`. Validate whether
the spike is expected traffic, a client retry loop or abuse. Tune explicit
production limits only after capacity review; never disable Redis-backed guards
as mitigation.

## Container CPU or memory pressure

These alerts require the operator's existing cAdvisor-compatible Docker
collector; the repository intentionally does not deploy one. Confirm that its
Docker label mapping matches the rule before enabling pages. For persistent
pressure, inspect the service-specific CPU/RAM limit, database pool utilization,
Redis memory and export queue first. Scale vertically before adding replicas;
use the rollback procedure in
[`docs/CAPACITY_PLANNING.md`](../../docs/CAPACITY_PLANNING.md), not an unbounded
`--scale` command against the public deployment.

## Backup/restore verification

There is no automatic metric for backup/restore verification because the
current verifier produces a one-off local report and no trusted persistent
timestamp. Do not invent a synthetic success gauge. Until a signed verification
artifact is persisted by a scheduled backup system, alert through that system's
own job status and retain its evidence.
