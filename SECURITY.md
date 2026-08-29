# Security policy

## Responsible disclosure

Do not open a public issue for a suspected vulnerability and do not include
production credentials, private URLs, personal data, object keys or live proof
of access. Until the project owner configures a verified private reporting
channel, report through the repository owner's pre-agreed private channel or a
GitHub private security advisory if it is enabled for this repository.

Include a minimal reproduction, affected revision/image digest, impact,
prerequisites and safe mitigation. The owner must acknowledge, triage, choose
severity, coordinate remediation and publish disclosure timing. This document
does not promise an SLA because no owner-operated security contact or response
policy has been configured in the repository.

## Supported versions

There is no released-version support window yet. Until the owner adopts a
release/versioning policy, the supported target is the latest reviewed commit
on the protected production branch and its immutable production image digests.
The owner must define semantic versioning, end-of-support dates and an upgrade
path before claiming support for a release. Historical untagged checkouts are
not automatically supported.

## Secret rotation and compromise response

Secrets belong in an approved deployment secret mechanism or a deployment-only
env file outside Git. Never place them in issues, logs, SBOMs, Trivy reports,
screenshots, command-line history or pull requests.

| Secret/material | Rotate when | Required follow-up |
| --- | --- | --- |
| PostgreSQL password / `DATABASE_URL` | Suspected exposure, staff departure, scheduled policy rotation | Update PostgreSQL and deployment secret atomically; validate backend/worker readiness |
| `JWT_SECRET_KEY` | Exposure or planned cryptographic rotation | Expect existing signed sessions to become invalid; communicate forced re-login |
| MFA Fernet key, recovery pepper, audit hash pepper | Exposure, custody change or policy rotation | Plan migration/invalidations before changing; do not rotate blindly because encrypted or hashed historic state may depend on the old material |
| S3 access key | Exposure, over-privilege finding, scheduled rotation | Create least-privilege replacement, test private bucket access, revoke old key, verify upload/download/export |
| SMTP password and Sentry DSN | Exposure or provider rotation | Replace in secret store and ensure sanitized telemetry/email behavior |
| Caddy/ACME account material | Account compromise or domain/certificate incident | Follow CA/account recovery procedure; preserve evidence and validate certificate chain |

Treat any suspected secret exposure as an incident: restrict access, capture
non-secret evidence, rotate/revoke, confirm affected services, audit access and
record the decision. Do not print old/new secret values to prove rotation.

## MFA and break-glass

Director and Super Admin require MFA. Recovery codes are one-time; privileged
MFA reset/recovery invalidates sessions and requires re-enrollment. Peer
recovery requires another Super Admin of the same organization and does not
grant a session directly.

Break-glass is a two-custodian, offline approval path for a sole Super Admin.
Keep raw approvals with separate custodians; only their SHA-256 hashes are
deployment configuration. Pass approvals through an approved protected console
mechanism, never shell history or command arguments. Record each use, verify
the matching audit events, rotate/re-enroll the factor and conduct a post-
incident review. Break-glass is not a routine password reset.

## Dependencies, SBOM and CVE exceptions

GitHub workflows pin Actions and container bases by immutable digest/SHA. The
`Supply chain security` workflow builds production images, emits SPDX SBOMs and
blocks High/Critical Trivy findings except documented temporary exceptions.
See [supply-chain security](docs/SUPPLY_CHAIN_SECURITY.md).

An exception in `.trivyignore` is permitted only when each CVE has an adjacent
`owner`, future `expires` date and tracked remediation reason. It must be
reviewed before expiry, removed when fixed and never used to hide a newly
introduced CVE. The security owner decides risk acceptance; maintainers do not
extend expiry solely to make CI green.

## Storage and audit limitations

Production files belong in a private TLS-verified S3-compatible bucket and are
served through authorized backend routes. The repository does not provision
bucket versioning, object lock, cross-region replication, lifecycle rules,
provider backups or IAM review; the owner must decide and verify each.

The PostgreSQL audit hash chain detects ordinary inconsistency but is not WORM
storage, a legal hold system or proof against an administrator with database
write access. Audit retention checkpoints preserve chain continuity after
cleanup, not independent immutability. See [data retention](docs/DATA_RETENTION.md).

## License status

No `LICENSE` file is supplied. The project owner must choose the license,
copyright holder and redistribution terms before publishing or distributing the
software. Do not infer a license from this repository's visibility.
