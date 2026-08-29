# Capacity planning and failure boundaries

This document defines the reviewed **small** production baseline in
`docker-compose.prod.yml` and the evidence needed before raising capacity. It
does not create Kubernetes, a managed database, a load balancer, or an HA
cluster. The external S3-compatible storage and the operator's monitoring
collector remain deployment responsibilities.

## Reviewed Compose limits

| Service | Small Compose limit / reservation | Purpose |
| --- | --- | --- |
| backend | 0.75 CPU / 768 MiB; 0.25 CPU / 384 MiB | One API replica in the supplied Compose deployment |
| export-worker | 1 CPU / 1 GiB; 0.5 CPU / 512 MiB | One renderer child at a time |
| PostgreSQL | 1 CPU / 1 GiB; 0.5 CPU / 512 MiB | `max_connections=80` |
| Redis | 0.5 CPU / 256 MiB; 0.25 CPU / 128 MiB | `maxmemory 192mb`, `noeviction` |
| frontend Nginx | 0.25 CPU / 128 MiB; 0.1 CPU / 64 MiB | Static assets and internal proxy |
| Caddy | 0.25 CPU / 128 MiB; 0.1 CPU / 64 MiB | TLS edge only |

`docker-compose.e2e.yml` contains smaller limits for its disposable PostgreSQL,
Redis and MinIO storage. They are test ceilings, not production sizing. The
production Compose deliberately uses external private S3-compatible storage;
do not treat the E2E MinIO instance as a production storage design.

## Database connection budget

The API uses SQLAlchemy `QueuePool` with `pool_pre_ping=true`, 30-second
checkout timeout and 30-minute recycle. Its default maximum is
`DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW = 10 + 5 = 15` per API replica.
The worker has a separate `2 + 0` pool, 15-second checkout timeout and the same
pre-ping/recycle behavior. A worker has one renderer child at a time; reserve
one extra active child connection per worker in the calculation.

Use this conservative formula before changing either pools or replica counts:

```text
required PostgreSQL connections =
  (API replicas × (DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW))
  + (worker replicas × (WORKER_DATABASE_POOL_SIZE + WORKER_DATABASE_MAX_OVERFLOW + 1 renderer))
  + migration / health / monitoring / operator reserve
```

The supplied `POSTGRES_MAX_CONNECTIONS=80` supports the reviewed medium upper
bound of two API replicas and two workers:
`2×15 + 2×(2+0+1) + 16 reserve = 52`, leaving 28 connections. Keep the result
below 80; do not fill all PostgreSQL slots. Changing `POSTGRES_MAX_CONNECTIONS`
also requires a PostgreSQL memory review, because each connection consumes
server resources even while application pools are idle.

Production startup requires every pool value to be supplied explicitly. This
prevents a new replica from silently inheriting an accidental default.

## Redis failure policy

Redis contains login throttling, upload/export resource guards, export queue
and worker heartbeat state. It runs `noeviction`, so security-critical keys are
never silently evicted. At the 192 MB Redis data ceiling (well below the 256 MiB
container limit) a write or connection failure returns a controlled `503`:

- login protection denies the login attempt;
- upload/export guards deny the protected operation;
- export queue creation/claiming fails rather than accepting untracked work.

This is intentionally fail-closed. Never change Redis to `allkeys-*` or
`volatile-*` eviction to silence the alert. Investigate TTL/key growth, retain
the data/OS headroom between `maxmemory` and the container limit, then perform
an explicit capacity change and recovery test.

## Deployment profiles

| Profile | Scope | Host starting point* | Database/Redis/disk | Replica boundary |
| --- | --- | --- | --- | --- |
| Small | Current reviewed Compose | 4 vCPU, 6 GiB RAM | PostgreSQL 50 GiB SSD minimum; external private object storage sized for retention plus 2× largest export; Redis 256 MiB | 1 API, 1 worker |
| Medium | After controlled staging evidence | 8 vCPU, 12 GiB RAM | PostgreSQL 100 GiB+ SSD and verified IOPS; Redis 512 MiB container / 384 MiB explicit `maxmemory`; object storage retention reviewed | Up to 2 API, 2 workers, only with an external health-checking LB/service discovery |

\*Host figures include a modest OS/engine margin; they are not a throughput
guarantee. Database backup retention, log retention and object storage lifecycle
policies are separate disk budgets.

The supplied frontend Nginx configuration addresses the Compose service name
and is not a substitute for a health-checking, replica-aware load balancer.
Therefore the default deployment is one backend. Do **not** claim availability
or run `--scale backend` in front of the static proxy without an external
health-checking LB/service-discovery configuration. Do not scale workers beyond
two until database connections, renderer CPU/RAM, Redis `noeviction` headroom,
object storage throughput and per-organization export limit have been measured.
Multiple workers are safe for durable jobs because PostgreSQL claims leases and
stale leases are requeued, but each costs one CPU and its documented DB budget.

## Saturation signals and alerts

The application exports pool size/checked-out/overflow/capacity, Redis
used/max memory, queue depth, worker heartbeat, storage operation results and
dependency state. `deployment/observability/prometheus-alerts.yml` pages or
warns for:

- API pool use above 80%;
- Redis data above 80% of its noeviction ceiling;
- sustained export backlog, stale worker, export failures and storage errors;
- PostgreSQL/Redis/S3 dependency failures.

Container CPU/RAM pressure rules are supplied for an existing
cAdvisor-compatible collector and deliberately deploy no collector or exposed
port. Validate its Docker label mapping before enabling those rules. Persistent
pool waits, PostgreSQL connection errors, Redis 503s, increasing queue depth,
worker heartbeat gaps, CPU throttling or memory near 85% are saturation signs.

## Scale-up and rollback order

1. Capture a staging baseline: request latency/5xx, pool occupancy, Redis
   memory, queue depth, worker CPU/RAM, PostgreSQL connections and S3 errors.
2. Remove application bottlenecks first: long transactions, pathological
   documents, retry loops or unnecessary object operations.
3. Increase a single vertical service limit with reserved host headroom and
   repeat the isolated load profile. For PostgreSQL, review the formula above
   before changing pool or connection values.
4. Only then add a replica behind an external health-checking LB and repeat the
   same profile; API max is two and worker max is two for the reviewed budget.
5. Roll back the last Compose/env change if SLOs regress: restore the prior
   reviewed values, wait for healthchecks, verify `/health/ready`, queue recovery
   and Redis guards. Do not delete PostgreSQL, Redis or Caddy volumes during a
   rollback.

## Isolated load and soak profile

Never run this profile against the existing development stack or a production
domain. Use a disposable environment with generated accounts/data, private test
storage and a unique Compose project name. The profile is intentionally modest:

| Stage | Duration / concurrency | Mix and acceptance observation |
| --- | --- | --- |
| Smoke | 5 min, 2 virtual users | Login, report read, revision-aware report save, 1 MiB allowed upload, export-job creation. No sustained 5xx, pool < 60%, Redis < 60%. |
| Baseline load | 30 min, 5 virtual users | 40% report reads, 25% saves, 15% logins, 10% uploads, 10% export-job creation. Verify queue drains, worker heartbeat stays fresh and guards keep working. |
| Soak | 2 h, 3 virtual users | Same realistic mix with a new export every 2 min. Track memory growth, PostgreSQL connections, Redis keys/memory, object-storage failures and completed job cleanup. |
| Failure drill | Once per staging run | Stop only the explicitly-created worker container, then start it again; verify stale lease recovery/requeue, no duplicate completed export and fresh heartbeat. Test Redis/storage unavailability as controlled 503s. |

Use a fresh project name, for example `$project = "pf-load-$([guid]::NewGuid().ToString('N').Substring(0,12))"` in PowerShell or `project="pf-load-$(date +%s)-$$"` in POSIX shell. Record the exact fixture sizes, client rates, host metrics and image digests with the result. The repository supplies configuration and unit/integration gates; it does not assert a production throughput number.
