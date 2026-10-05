# Operations runbook

Use this alongside the alert-specific
[observability runbook](../deployment/observability/RUNBOOK.md). Start an
incident record with time, service, alert, change correlation and safe request
ID hash. Do not collect secrets, tokens, object keys, raw document content or
customer data in monitoring notes.

## First five minutes

1. Confirm scope: one tenant, one service, all API traffic or only exports.
2. Check `/health/ready`, worker heartbeat, current deploy/change record and
   the safe Prometheus dependency/queue/pool/Redis gauges.
3. Preserve relevant aggregate metrics and container status; avoid dumping
   production environment variables or application logs with sensitive context.
4. Declare severity and notify the owner/on-call escalation path defined by
   the organization. This repository does not define people, contact details or
   an incident SLA.

## Redis unavailable or memory pressure

Expected behavior is fail-closed: login protection, upload/export guards and
export queue operations can return controlled `503` rather than silently
evicting security-critical state.

- Check service health, DNS/network path, Redis memory gauge and `noeviction`
  configuration. Do not change the policy to an eviction mode to clear an
  alert.
- Check for unexpected key/TTL growth and recent deployment/config changes.
- Scale only after validating host headroom and the reviewed capacity profile.
- Do **not** run `FLUSHALL`/`FLUSHDB`. Restarting Redis clears rate-limit,
  guard, queue and heartbeat state; treat it as an incident decision and then
  verify login protection, resource guard, queue recovery and worker heartbeat.
- If queue notification state was lost, durable PostgreSQL jobs remain the
  source of truth; recover workers after Redis is healthy.

## PostgreSQL unavailable, saturated or slow

- Check PostgreSQL health, disk/IOPS, connection count, long transactions,
  application pool occupancy and recent migrations.
- Do not raise `max_overflow` or `max_connections` as an immediate mitigation.
  Use the connection formula in [capacity planning](CAPACITY_PLANNING.md).
- Keep failed writes unavailable rather than routing them to another database.
  There is no database failover/managed cluster in this repository.
- If integrity, corruption or a failed incompatible migration is suspected,
  stop normal change activity and escalate to the approved restore decision.

## S3-compatible storage error

Teaching material deletion can return MATERIAL_DELETE_PENDING after access
has been revoked. Once storage recovers, retry DELETE for that material as its
Teacher owner; preserve the tombstone. Pending bytes remain in the tenant
storage budget until removal is confirmed.
See [curriculum operations](DISCIPLINES.md#rollout-rollback-and-remaining-boundaries)
for lost-acknowledgement orphan handling and migration rollback.

- Validate the storage dependency gauge, endpoint DNS/TLS, private bucket
  policy, credential rotation status, provider status and object-storage quota.
- Keep affected upload/download/export behavior unavailable (`503`); do not
  make the bucket public or switch production to local filesystem storage.
- Check whether completed jobs can be retried safely before changing their
  status. Preserve failed-object evidence according to the incident policy,
  never in public logs.
- For a provider outage, apply the owner-approved RTO/communication plan; the
  repository does not provide multi-region S3 failover.

## Worker or export failure

1. Check `export-worker` healthcheck, heartbeat age, queue depth, terminal job
   transitions, renderer CPU/RAM and Redis/PostgreSQL/S3 dependency state.
2. Confirm the worker has a graceful stop window. Restart only the intended
   production worker service through the approved deployment command; do not
   stop PostgreSQL, Redis or unrelated projects.
3. On startup, the worker requeues queued and expired-lease running jobs.
   PostgreSQL claims prevent duplicate completion; inspect job state before
   manually retrying any job.
4. For timeout/cancel patterns, reproduce using sanitized test data in an
   isolated environment before raising rendering timeouts or concurrency.
5. Escalate when stale leases do not recover, artifacts are missing after a
   claimed success, or a cross-tenant access concern exists.

## Alert response

| Alert class | Initial action | Escalate when |
| --- | --- | --- |
| HTTP 5xx / latency | Correlate with dependencies, deploy and pool metrics | Sustained SLO breach, auth/tenant/storage impact |
| Pool exhaustion | Find long transactions and capacity mismatch | PostgreSQL errors or >80% occupancy persists |
| Redis memory | Preserve fail-closed behavior; investigate growth | Repeated `503`, no headroom or queue impact |
| Worker backlog/heartbeat | Check worker health and durable jobs | No recovery after worker restart or backlog keeps growing |
| Storage errors | Validate provider/TLS/credentials | Data access loss, unauthorized access concern or provider outage |
| CPU/RAM pressure | Confirm collector labels and service saturation | OOM/restarts, throttling or capacity exhaustion |

Thresholds are starting values and must be tuned after an owner-approved
staging soak test. Collector-based CPU/RAM alerts require the operator's
existing cAdvisor-compatible collector; this repository does not deploy it.

## Backup and restore

Follow the existing backup/restore sections in [README](../README.md) and
[data retention](DATA_RETENTION.md). Before restoring:

- obtain incident/change approval and identify the exact backup bundle;
- verify manifest checksum, backup age and target environment;
- restore only to an empty target as enforced by the supplied script;
- separately restore/verify the private S3 object set when production uses S3;
- run migrations/health/smoke checks before directing users to the restored
  environment.

The supplied local-volume scripts are not a complete S3 backup or a tested
disaster-recovery solution by themselves. Never overwrite a non-empty
production target as an experiment.

## Escalation and closure

Escalate immediately for suspected credential exposure, unauthorized tenant
access, audit-chain invalidity, lost/incorrect data, public storage exposure,
MFA bypass, certificate compromise or restoration failure. The owner must
define named incident roles, legal/privacy notification requirements, severity
thresholds and out-of-hours contact path.

Close only after service health, relevant smoke checks, alert recovery, data
integrity/backup implications, root cause, customer communication decision and
follow-up owner are recorded.
