# Curriculum validation

Validation ran on Windows with Python 3.14 from the existing backend virtual
environment, Node.js and a newly initialized PostgreSQL 18 cluster bound only
to loopback. Databases were disposable and separate from development/production:
curriculum_test, curriculum_additional_test and curriculum_migration_test.
No existing database or user working tree was reset.

Architecture, new files, permissions, storage, rollout and limitations are
documented in [the module design](DISCIPLINES.md).

## Executed checks

Commands below use python for the virtual-environment Python executable.
Backend checks ran from backend unless indicated otherwise.

| Command | Actual result |
| --- | --- |
| python -m ruff check app seed.py e2e_seed.py | Passed |
| python -m mypy app/core app/rate_limit app/observability app/middleware.py app/api/pagination.py | Passed, 14 source files |
| python -m pytest app/tests unit_tests -q --tb=short | 375 passed, 2 failed due to missing native Windows PDF dependencies |
| python -m pytest app/tests/test_disciplines.py unit_tests/test_docx_preflight.py unit_tests/test_document_submission_limits.py -q --tb=short | 60 passed: 23 curriculum and 37 OOXML/multipart tests |
| python -m pip_audit -r requirements.txt | No known vulnerabilities |
| python -m alembic upgrade head | Complete migration chain applied successfully |
| python -m alembic check | No new upgrade operations |
| python -m alembic downgrade 5d6e7f8091a2, then upgrade head and check | New migration rollback/reapply succeeded, no drift |
| npm ci | Completed without changing lockfile |
| npm run lint | Passed with pre-existing warnings outside the new feature |
| npm test | 149 passed across 28 files |
| npm test -- src/features/disciplines/DisciplinePages.test.tsx | 10 passed, repeated after final UI changes |
| npm run build | TypeScript and Vite passed; existing large-chunk warning remains |
| npm audit --audit-level=high | No vulnerabilities |
| npx playwright test disciplines.spec.ts --list | New acceptance scenario discovered successfully; browser execution not performed locally |
| python scripts/verify_documentation.py (root) | Passed |
| git diff --check (root) | Passed |
| python scripts/verify_container_security.py (root) | Failed on existing expired CVE exceptions |

The full backend run collected the initial 20 curriculum cases. Three additional
storage/template regressions were subsequently added and all 23 curriculum
cases passed in the separate targeted run. No test count is inferred for a
command that was not rerun.

The two full-suite failures are
TestPdfExport.test_export_produces_valid_pdf_with_expected_text and
TestPdfExport.test_export_audit_logged. Both fail loading libgobject-2.0-0 before
WeasyPrint can render. No curriculum failure occurred.

## Coverage and outstanding gates

Backend covers Teacher creation/persistence, Student denial and revoked
membership, rejected client tenant/owner fields, cross-tenant and same-tenant
owner isolation, foreign/unassigned groups, composite database constraints,
topic edit/order/archive, all three original formats, an existing presentation
template, invalid/macro/unsafe files, byte/envelope limits, upload retries,
private download headers, shared quota, orphan cleanup, lost commit
acknowledgements, retryable deletion and storage migration selection.

Frontend covers creation/navigation, topic goals, loading and missing
resources, client upload limits, double-submit prevention, uncertain upload
retries, query invalidation, pending deletion, archived content, mismatched
topic URLs, all locales and organization-separated query cache.

The added Playwright scenario performs Teacher login, discipline/topic creation,
three uploads, reload, download byte comparison, foreign-tenant 404 and Student
denial against deterministic E2E fixtures. The repository's disposable Compose
E2E stack could not run locally because Docker daemon requests did not complete.
No development/production endpoint was substituted.

PR #29 already has failed mandatory gates: E2E cannot pull minio/minio, and the
supply-chain policy rejects expired .trivyignore exceptions. This module retains
those gates and depends on that baseline. New PR checks must be reviewed on its
verified head before merge; no successful merge is claimed here.
