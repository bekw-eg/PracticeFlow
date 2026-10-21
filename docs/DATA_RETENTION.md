# Data retention, backup and recovery boundaries

Curriculum archive retains discipline/topic metadata and materials. Explicit
material deletion revokes access before removing the private file; tombstones
remain in PostgreSQL, and failed removal retains the storage quota until retry.
See [curriculum storage and rollback](DISCIPLINES.md#upload-and-deletion).

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
| PostgreSQL backup | Coordinated production DB/S3 workflow provides a daily systemd timer template, encrypted off-site restic storage, checksums and configurable retention (30 days, minimum seven copies). Deployment is not yet verified. | Actual vault/credentials, maintenance window, alerting, approved retention and production restore drill |
| S3-compatible objects | All current objects join the coordinated backup. Provider versioning/replication/object lock and historic versions remain external. | Provider policy, independent failure domain, lifecycle, key management and production restore tests |
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

The repository provides local-volume helpers and the separate
[coordinated production backup workflow](PRODUCTION_BACKUPS.md). The latter
includes scheduling templates, encrypted off-site storage integration, complete
current S3 object copying, safe retention and a reproducible isolated restore
drill. Actual production infrastructure/keys and installation remain operator
inputs. Local-volume helpers alone do not cover production S3.

For production S3, verify database metadata and S3 objects as a coordinated
backup set. Provider-side versioning, replication or immutable retention must
be configured and tested by the owner. Do not assume a PostgreSQL dump contains
objects, and do not assume an object-store export contains database metadata.

Use the [release runbook](RELEASE_RUNBOOK.md) for pre-deploy backups and the
[operations runbook](OPERATIONS_RUNBOOK.md) for incident restoration. Restore
only to an approved empty target; never test a restore by overwriting a live
environment.

## Group review presentation retention

Group review presentation drafts, immutable snapshots and generated private
PPTX files are retained without an automatic TTL. Include `group_review_reports`
and their private storage objects in coordinated backups and tenant retention
planning. Source DOCX retention cleanup does not delete these reports. See
[group review presentations](GROUP_REVIEW_PRESENTATIONS.md) for access,
generation and migration rollback boundaries.

The copy-only LocalStorage-to-S3 migration tool also includes generated group
reports, preserving their object keys and verifying the copied bytes. Apply the
current schema before running it; drafts do not have storage objects.

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
