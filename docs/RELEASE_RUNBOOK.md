# Production release runbook

This is an operator checklist, not an automated deployment system. Use the
approved change window, real deployment project name and approved secret
mechanism. Do not paste a production env file or secret value into a ticket,
terminal recording or CI log.

## 1. Pre-deploy decision

- Record change owner, reviewer, deployment window, target commit/image digest
  and explicit rollback owner.
- Confirm the owner has chosen the production domain, Caddy email, trusted
  proxy chain, monitoring CIDR, backup destination, S3 retention/versioning and
  branch protection required checks. The repository does not choose these.
- Review [capacity planning](CAPACITY_PLANNING.md): current replica count,
  PostgreSQL connection budget, Redis headroom and deployment host capacity.
- Review the release diff for migrations, secret/config additions, retention
  impact, privilege changes and runbook updates.
- Verify a tested backup exists and that its restoration objective is within
  the owner-approved RPO/RTO. A successful backup command alone is not proof of
  restorability.

## 2. GitHub CI and supply-chain gate

Before approval, require successful relevant checks:

- backend lint, type checks, migrations/schema drift and tests;
- frontend `npm ci`, lint, tests, production build and audit;
- isolated E2E integration;
- capacity configuration and documentation link checks;
- `Supply chain security / Build, attest and scan production images`.

Review the attached SPDX SBOM and Trivy reports. High/Critical findings block
the release unless a still-valid, owner/reason/expiry-documented exception is
in `.trivyignore`. Do not waive a failed CVE gate in a release note. If a
registry image is actually published, use the keyless Cosign/OIDC template only
with an immutable `@sha256:` reference after owner approval; this repository
does not publish images automatically. See
[supply-chain security](SUPPLY_CHAIN_SECURITY.md).

## 3. Backup and migration plan

1. Verify database backup age, checksum, encryption/access control and a
   previously tested restore procedure. For production S3, separately verify
   provider versioning/replication/export; local-volume backup tooling is not a
   complete S3 backup.
2. Capture baseline `/health/ready`, worker heartbeat, queue depth, database
   pool, Redis memory and storage error metrics. Preserve only safe aggregate
   evidence.
3. Classify migrations as backward compatible, expand/contract, or requiring a
   maintenance window. Never assume `alembic downgrade` is a safe production
   rollback.
4. For a compatible migration, deploy the reviewed image/config, run the
   migration once against the intended database and wait for service health.
   For a destructive or incompatible migration, get an explicit maintenance,
   restore and rollback plan before continuing.

Run the configuration check before traffic is moved:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  -f deployment/caddy/docker-compose.caddy.yml config --quiet
```

The actual deploy command, Compose project name and image source are
environment-specific; reuse the approved deployment procedure rather than
inventing a new project during a release.

## 4. Caddy and TLS validation

Before external traffic, validate the bundled Caddy configuration in the
approved deployment context:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  -f deployment/caddy/docker-compose.caddy.yml \
  run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

After deployment, manually confirm from approved networks:

- HTTP redirects to the owner-approved HTTPS domain;
- certificate hostname/chain and HSTS are correct;
- backend, PostgreSQL, Redis and worker healthchecks are healthy;
- `/metrics` is reachable from the configured monitoring CIDR and returns
  `403` from an unapproved source;
- no direct backend, frontend, PostgreSQL or Redis port is public.

Public DNS, ACME issuance, firewall exposure, CDN/LB behavior and monitoring
network reachability require the real environment; local Compose validation
cannot certify them.

## 5. Post-deploy smoke test

Use a non-production test account in the intended tenant and avoid real student
documents. Confirm:

1. login and, for a privileged account, MFA challenge/verification;
2. authenticated report read and revision-aware save;
3. authorized image upload/download through the API;
4. export-job creation, worker completion and authorized artifact download;
5. audit event visibility/integrity for a Super Admin in the same tenant;
6. no unexpected 5xx, pool saturation, Redis memory pressure, worker backlog
   or storage error alert.

Record timing and safe outcome statuses. Do not attach tokens, cookies,
document contents, raw URLs, object keys or credentials to the release record.

## 6. Rollback decision points

Stop and roll back the last compatible application/config change when any of
the following occurs: failed migration/readiness, authentication or MFA break,
cross-tenant authorization concern, persistent 5xx, unrecoverable worker queue
growth, Redis fail-closed errors outside an approved incident, private storage
failure, or invalid Caddy/TLS boundary.

- **Before an incompatible migration:** restore the prior image/config only
  after confirming the prior schema compatibility.
- **After an incompatible migration:** do not force a downgrade. Escalate to
  the approved database restore plan and incident owner.
- **For worker failures:** first keep the durable PostgreSQL job state intact;
  use the worker recovery procedure in [operations runbook](OPERATIONS_RUNBOOK.md).
- **Never** use `down --volumes`, delete PostgreSQL/Redis/Caddy data or flush
  Redis as a rollback shortcut.

Close the release only after smoke-test evidence, alert review, backup status
and decision log are complete.
