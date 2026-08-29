# Contributing to PracticeFlow

## Before you start

Do not commit `.env` files, production credentials, backup bundles, exported
documents, real tenant data, SBOMs containing deployment context or private
incident evidence. Use the deterministic development seed only locally and
never copy its credentials to a production environment.

The canonical local setup, disposable test Compose commands and browser E2E
flow are in [README](README.md). Test Compose projects must use a newly
generated `--project-name`; clean up only the project created by that command.
Never run `docker compose down` without the intended project name near another
developer's stack.

## Local workflow

1. Install Docker Compose v2, or Python 3.12/PostgreSQL 16 and Node.js 22.
2. For the normal development stack, copy `.env.example` to `.env` and run
   `docker compose up --build` as documented in the README.
3. For backend changes, install `backend/requirements-dev.txt`; for frontend
   changes, run `npm ci` in `frontend`. Keep lockfiles intact: use `npm ci` in
   CI-equivalent checks and commit a lockfile only with the intentional package
   change.
4. Keep migrations in Alembic. Generate/review a migration for schema changes,
   apply `alembic upgrade head` to a disposable database, and run
   `alembic check`. Do not edit an already-applied migration to change production
   history.

## Required validation

Run the relevant checks before requesting review:

```bash
cd backend
ruff check app seed.py e2e_seed.py
mypy app/core app/rate_limit app/observability app/middleware.py app/api/pagination.py
pytest app/tests -q
pip-audit -r requirements.txt

cd ../frontend
npm ci
npm run lint
npm test
npm run build
npm audit --audit-level=high
```

Also run `python scripts/verify_capacity_configuration.py` from repository root
when editing Compose/deployment/observability configuration, and run the
documentation check when editing Markdown. The full containerized test command
and E2E profile remain in the README; they intentionally use an isolated
Compose project and must not target production data.

## Pull request rules

- Keep a PR narrowly scoped; explain behavior, security, migration and
  operational effects in the PR template.
- Add or update tests for behavior changes. A schema change needs migration,
  upgrade/check evidence and rollback/compatibility explanation.
- Preserve tenant scoping and server-side authorization. UI controls are not an
  authorization boundary.
- Do not weaken Redis fail-closed guards, S3 privacy, audit safety, immutable
  image/action pinning, dependency gates or documentation checks without
  explicit security review.
- Update runbooks when a deployment variable, alert, retention rule, backup
  procedure, trust boundary or operator action changes.
- Never put a real production hostname, email, IP/CIDR, credential or GitHub
  username into an example/template unless the owner explicitly authorizes it.

## CI and review gates

Required checks should include backend tests/migration drift, frontend
lint/test/build/audit, E2E integration, supply-chain SBOM/CVE gate, capacity
policy and documentation links. GitHub branch protection/rulesets are owned by
the repository administrator and cannot be enabled by workflow YAML alone.

Reviewers should use `.github/CODEOWNERS.example` only as a starting template:
the owner must replace placeholders with real authorized users or teams before
creating an actual `CODEOWNERS` file.
