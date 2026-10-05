# Data retention, backup and recovery boundaries

Retention is a deployment and legal-policy decision. The values below describe
current application defaults only; they are not a legal retention schedule,
automatic backup policy or promise of recovery objective.

## Current application behavior

Teacher document originals have an explicit owner-controlled lifecycle. Archive
hides a submission from the active list and from the local comparison corpus;
it does not remove history. Deleting an original first records a durable
pending-removal state, then removes only the DOCX object after storage confirms
the operation. Completed checks, paragraph excerpts, settings snapshots and
audit events remain available. A storage failure leaves the request retryable
and does not release quota. Active checks block the operation.

| Data | Current behavior | Owner decision still required |
| --- | --- | --- |
| Original uploaded images | No repository-wide automatic deletion period is configured. Objects remain while their authorized application record remains. | Legal basis, user deletion workflow, lifecycle/versioning and hold policy |
| Teacher original DOCX | Owner can archive or request original removal; removal keeps immutable submission metadata and check history, and is retryable if storage is unavailable. | Legal hold, recovery window and whether retained excerpts/index text meet policy |
| Completed export artifact and terminal job | `EXPORT_JOB_RETENTION_SECONDS=86400` (24 hours) in the production example; worker cleanup removes expired terminal artifact/job state. | Whether 24 hours meets business/legal needs; export archival and incident hold procedure |
| Audit trail | `AUDIT_RETENTION_DAYS=365`; cleanup creates a retention checkpoint for the remaining application hash chain. | Required duration, legal hold, archive destination, access review and evidence policy |
| PostgreSQL backup | Scripts can create/check a local-volume bundle with manifest checksums. No schedule is configured. | Frequency, encryption, immutable/off-site location, monitoring and restore testing |
| S3-compatible objects | Production S3 is external; repository does not configure replication/versioning/object lock or a backup job. | Provider versioning, replication/export, lifecycle, key management and restore tests |
| Application/proxy/monitoring logs | No repository retention or external collector is provisioned. Logs intentionally omit sensitive values where possible. | Collector, encryption/access, retention, deletion and legal/privacy policy |
| SBOM/Trivy/CI artifacts | Workflow artifact retention is configured by its workflow and is not a system-data backup. | Access, retention and evidence requirements in GitHub/CI platform |

Changing a production environment value changes behavior only after the normal
review/release process. Record the approved value, legal basis and effective
date; do not silently change it during an incident.

## RPO and RTO

No production RPO or RTO is established by this repository. The project owner
must set both after assessing service criticality, backup frequency, storage
durability, restoration practice and dependency-provider commitments.

| Objective | Meaning | Evidence needed before claiming it |
| --- | --- | --- |
| RPO | Maximum acceptable data loss measured in time | Backup frequency, PostgreSQL/S3 consistency scope, successful restore timestamp and exception handling |
| RTO | Maximum acceptable service-recovery time | Timed restore drill including database, private storage, migrations, Caddy/TLS and smoke test |

A checksum-valid backup is not a measured RPO/RTO. The owner should conduct a
regular isolated restore exercise, record duration and data point recovered,
and update the objective or implementation when evidence does not meet policy.

## Backup and restore procedure boundaries

The repository provides local-volume backup/restore helpers and a disposable
verification configuration. They protect against accidental misuse by requiring
a checksum-valid bundle and an empty restore target, but they do not configure
backup scheduling, encryption, off-site storage or production S3 copying.

For production S3, verify database metadata and S3 objects as a coordinated
backup set. Provider-side versioning, replication or immutable retention must
be configured and tested by the owner. Do not assume a PostgreSQL dump contains
objects, and do not assume an object-store export contains database metadata.

Use the [release runbook](RELEASE_RUNBOOK.md) for pre-deploy backups and the
[operations runbook](OPERATIONS_RUNBOOK.md) for incident restoration. Restore
only to an approved empty target; never test a restore by overwriting a live
environment.

## Audit immutability limitation

The application audit trail is hash chained in PostgreSQL and can detect many
consistency breaks within the retained segment. It is **not** true WORM storage:

- a database/deployment administrator can alter tables, code or hash anchors;
- repository backups do not independently attest the audit chain;
- normal retention cleanup removes old rows and preserves continuity only via
  an application checkpoint;
- no external timestamp authority, immutable object lock, write-once ledger or
  legal-hold workflow is provisioned here.

If regulation requires tamper-resistant or WORM audit evidence, the owner must
choose an independent immutable archive, retention/legal-hold design, access
separation, export cadence and verification procedure. This is an external
governance/infrastructure decision, not a claim satisfied by the current
PostgreSQL hash chain.
