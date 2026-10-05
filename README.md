# PracticeFlow

PracticeFlow — multi-tenant система управления учебной практикой: организации, пользователи и роли, группы, практики, шаблоны документов, отчёты студентов, рецензирование, комментарии и экспорт DOCX/PDF.

Backend — FastAPI, SQLAlchemy 2, Alembic и PostgreSQL. Frontend — React 19, TypeScript и Vite. Tenant определяется сервером из текущей активной membership; клиент не передаёт `organization_id` для перенаправления tenant-scoped операций.

## Production documentation

- [Architecture and trust boundaries](docs/ARCHITECTURE.md)
- [Security policy](SECURITY.md)
- [Contribution and CI requirements](CONTRIBUTING.md)
- [Release runbook](docs/RELEASE_RUNBOOK.md)
- [Operations runbook](docs/OPERATIONS_RUNBOOK.md)
- [Data retention and recovery boundaries](docs/DATA_RETENTION.md)
- [Role and tenant-boundary matrix](docs/ROLE_MATRIX.md)
- [Capacity planning](docs/CAPACITY_PLANNING.md)
- [Supply-chain security](docs/SUPPLY_CHAIN_SECURITY.md)

`LICENSE` намеренно отсутствует: правообладатель должен отдельно выбрать
лицензию и условия распространения до публикации или distribution.

## Требования

- Docker Desktop / Docker Engine с Compose v2 — рекомендуемый способ;
- либо Python 3.12, PostgreSQL 16 и Node.js 22;
- для production — внешний TLS reverse proxy (Caddy, Nginx, Traefik или ingress).

## Development в Docker

Development Compose публикует PostgreSQL только на loopback, запускает FastAPI с hot reload и Vite dev server. Demo seed разрешён исключительно при `ENV=development`.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Linux/macOS:

```bash
cp .env.example .env
docker compose up --build
```

Адреса:

- frontend: `http://localhost:5173`;
- API: `http://localhost:8000/api/v1`;
- Swagger: `http://localhost:8000/docs`;
- liveness/readiness: `http://localhost:8000/health/live` и `/health/ready`;
- метрики: `http://localhost:8000/metrics`.

`.env.example` содержит только локальные development-реквизиты. Файл `.env` исключён из Git. Не используйте development значения в production.

### Development seed

При `ENV=development` и `SEED_ON_START=true` создаются demo-аккаунты организации `demo-university`. Их общий пароль `Practice123!` предназначен только для локальной разработки:

- `superadmin@demo.edu` — Super Admin;
- `director@demo.edu` — Director;
- `teacher@demo.edu` — Teacher;
- `student1@demo.edu` … `student7@demo.edu` — Student.

Entrypoint и `seed.py` отказываются загружать эти данные при любом `ENV`, кроме `development`. В production `SEED_ON_START` принудительно равен `false`.

## Локальный запуск без Docker

Сначала создайте отдельную локальную PostgreSQL database и задайте `DATABASE_URL` с host `localhost`.

Windows PowerShell — backend:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:ENV = "development"
$env:DATABASE_URL = "postgresql+psycopg://practiceflow:practiceflow@localhost:5432/practiceflow"
$env:JWT_SECRET_KEY = "dev-secret-change-me-before-any-real-deployment"
alembic upgrade head
python seed.py
uvicorn app.main:app --reload
```

Linux/macOS — backend:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export ENV=development
export DATABASE_URL='postgresql+psycopg://practiceflow:practiceflow@localhost:5432/practiceflow'
export JWT_SECRET_KEY='dev-secret-change-me-before-any-real-deployment'
alembic upgrade head
python seed.py
uvicorn app.main:app --reload
```

Frontend на обеих платформах:

```bash
cd frontend
npm ci
npm run dev
```

## Тесты и миграции

Backend tests требуют явный `TEST_DATABASE_URL`. Имя database обязано оканчиваться на `_test`, а URL не может совпадать с `DATABASE_URL`; иначе suite аварийно завершится до очистки таблиц.

Полностью контейнерный запуск на Windows и Linux:

```bash
TEST_PROJECT="pf-test-$(date +%s)-$$"
docker compose --project-name "$TEST_PROJECT" -f docker-compose.test.yml up -d --wait test-db
docker compose --project-name "$TEST_PROJECT" -f docker-compose.test.yml --profile test run --rm backend-test
docker compose --project-name "$TEST_PROJECT" -f docker-compose.test.yml down --volumes --remove-orphans
```

В PowerShell создайте равнозначное уникальное имя: `$testProject = "pf-test-$([guid]::NewGuid().ToString('N').Substring(0,12))"`, затем передавайте `$testProject` в каждый `--project-name`. Test PostgreSQL использует `tmpfs`, не подключает dev/prod volumes и доступен только на `127.0.0.1:5433`. Cleanup разрешён только для project name, сгенерированного этим запуском; не выполняйте `down` без него рядом с development stack.

Запуск backend tests с host-машины — Windows PowerShell:

```powershell
Set-Location backend
$env:ENV = "test"
$env:DATABASE_URL = "postgresql+psycopg://practiceflow_test:practiceflow_test_local_only@localhost:5433/practiceflow_app_unused"
$env:TEST_DATABASE_URL = "postgresql+psycopg://practiceflow_test:practiceflow_test_local_only@localhost:5433/practiceflow_test"
$env:JWT_SECRET_KEY = "test-only-secret-that-is-never-used-in-production"
pytest app/tests -q
```

Linux/macOS:

```bash
cd backend
export ENV=test
export DATABASE_URL='postgresql+psycopg://practiceflow_test:practiceflow_test_local_only@localhost:5433/practiceflow_app_unused'
export TEST_DATABASE_URL='postgresql+psycopg://practiceflow_test:practiceflow_test_local_only@localhost:5433/practiceflow_test'
export JWT_SECRET_KEY='test-only-secret-that-is-never-used-in-production'
pytest app/tests -q
```

Проверка полной цепочки миграций и schema drift использует вторую одноразовую database:

```bash
MIGRATION_PROJECT="pf-migration-$(date +%s)-$$"
docker compose --project-name "$MIGRATION_PROJECT" -f docker-compose.test.yml --profile migration up -d --wait migration-db
docker compose --project-name "$MIGRATION_PROJECT" -f docker-compose.test.yml --profile test --profile migration run --rm -e DATABASE_URL=postgresql+psycopg://practiceflow_test:practiceflow_test_local_only@migration-db:5432/practiceflow_migration_test backend-test alembic upgrade head
docker compose --project-name "$MIGRATION_PROJECT" -f docker-compose.test.yml --profile test --profile migration run --rm -e DATABASE_URL=postgresql+psycopg://practiceflow_test:practiceflow_test_local_only@migration-db:5432/practiceflow_migration_test backend-test alembic check
docker compose --project-name "$MIGRATION_PROJECT" -f docker-compose.test.yml down --volumes --remove-orphans
```

Frontend checks:

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
npm audit --audit-level=high
```

Backend static/dependency checks:

```bash
cd backend
ruff check app seed.py e2e_seed.py
mypy app/core app/rate_limit app/observability app/middleware.py app/api/pagination.py
pip-audit -r requirements.txt
```

### Browser E2E regression

Playwright запускается только против отдельного disposable Compose project: PostgreSQL находится в `tmpfs`, backend применяет миграции при старте, затем при `ENV=e2e` загружает ровно два deterministic tenant fixture. Никакие development/production database, volume, секреты или внешний URL для этого не используются. Frontend собирается обычным production Dockerfile и раздаётся встроенным Nginx; Vite dev server в сценарии отсутствует.

Windows PowerShell:

```powershell
$e2eProject = "pf-e2e-$([guid]::NewGuid().ToString('N').Substring(0,12))"
docker compose --project-name $e2eProject -f docker-compose.e2e.yml up --build --wait
Set-Location frontend
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:4173"
npm ci
npx playwright install chromium
npm run test:e2e
Set-Location ..
docker compose --project-name $e2eProject -f docker-compose.e2e.yml down --volumes --remove-orphans
```

Linux/macOS:

```bash
E2E_PROJECT="pf-e2e-$(date +%s)-$$"
docker compose --project-name "$E2E_PROJECT" -f docker-compose.e2e.yml up --build --wait
cd frontend
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:4173
npm ci
npx playwright install chromium
npm run test:e2e
cd ..
docker compose --project-name "$E2E_PROJECT" -f docker-compose.e2e.yml down --volumes --remove-orphans
```

Если port `4173` занят, перед `up` задайте `E2E_FRONTEND_PORT` и передайте такой же URL в `PLAYWRIGHT_BASE_URL`.

`frontend/e2e/qa-regression.spec.ts` повторяет regression BUG-001/002/003. `frontend/e2e/ci-critical.spec.ts` дополнительно проверяет anonymous `401`, login, UI role routing, `403` для teacher-only API и отсутствие cross-tenant disclosure (`404` для report другого tenant). При падении Playwright сохраняет trace, screenshot и video, а CI прикладывает их вместе с HTML report.

`docker-compose.e2e.yml` также поднимает непубличный disposable MinIO и создаёт bucket через одноразовый `minio-init`. CI запускает `app/s3_integration_tests` против этого MinIO (streaming round-trip и cleanup), а Playwright проверяет authorized image upload/download, cross-tenant `404` и worker-generated DOCX download через тот же bucket.

## Production deployment

`docker-compose.prod.yml` не содержит development credentials, не публикует PostgreSQL/Redis/backend/frontend, не использует bind mounts, local `backend_storage` volume или seed. Backend и отдельный `export-worker` работают non-root и используют один private S3-compatible bucket; frontend собирается через `npm ci` и раздаётся unprivileged Nginx. В production он запускается вместе с Caddy template ниже: только Caddy публикует `80` и `443`.

Профили CPU/RAM, connection budget, Redis `noeviction`, разрешённая горизонтальная шкала, признаки saturation, isolated load/soak profile и rollback описаны в [capacity planning](docs/CAPACITY_PLANNING.md). Базовый Compose deployment запускает **одну** API и **одну** worker replica; не используйте `--scale backend` без внешнего health-checking load balancer/service discovery.

Создайте deployment env вне Git.

Windows PowerShell:

```powershell
Copy-Item .env.production.example .env.production
# Заполните обязательные пустые значения в .env.production.
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
docker compose --env-file .env.production -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml up -d --build
```

Linux/macOS:

```bash
cp .env.production.example .env.production
# Заполните обязательные пустые значения; JWT_SECRET_KEY можно создать так:
openssl rand -hex 32
docker compose --env-file .env.production -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml up -d --build
```

Обязательные production значения:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — уникальные deployment credentials;
- `DATABASE_URL` — полный SQLAlchemy URL до internal service `postgres`; спецсимволы пароля должны быть URL-encoded;
- `POSTGRES_MAX_CONNECTIONS=80` и все `DATABASE_*` / `WORKER_DATABASE_*` pool values — явный reviewed connection budget; формула и safe upper bound приведены в [capacity planning](docs/CAPACITY_PLANNING.md#database-connection-budget). Не повышайте pool overflow как реакцию на timeout;
- `JWT_SECRET_KEY` — случайный секрет минимум 32 байта, не placeholder/default;
- `MFA_TOTP_ENCRYPTION_KEY` — отдельный Fernet key для шифрования TOTP secrets; создаётся один раз командой `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` и не должен совпадать с development key;
- `MFA_RECOVERY_CODE_PEPPER` — отдельный случайный секрет (минимум 32 bytes) для HMAC recovery codes;
- `MFA_BREAK_GLASS_KEY_A_HASH`, `MFA_BREAK_GLASS_KEY_B_HASH` — SHA-256 hashes двух независимых offline approvals. Raw значения находятся у разных custodians и никогда не попадают в Compose env file, логи или command line;
- `CORS_ORIGINS` — JSON-массив точных HTTPS origins, например `["https://practice.example"]`;
- `FRONTEND_URL` — публичный HTTPS URL;
- `COOKIE_SECURE=true`, `SEED_ON_START=false`, Redis rate limiter, Redis resource guard и Redis export queue задаются production Compose и дополнительно проверяются приложением.
- `APP_NETWORK_NAME`, `APP_NETWORK_SUBNET` — имя и **неиспользуемая** private Docker subnet для deployment; значения выбирает deployer;
- `FRONTEND_PROXY_IP`, `CADDY_PROXY_IP` — два различных статических адреса внутри этой subnet;
- `TRUSTED_PROXY_IPS` — comma-separated allow-list ровно этих proxy hops. Не используйте `*` и не включайте широкую сеть, в которой могут находиться клиенты;
- `PRACTICEFLOW_DOMAIN`, `CADDY_EMAIL` — реальный публичный hostname и адрес для ACME; репозиторий не задаёт ни домен, ни сертификат;
- `METRICS_ALLOWED_CIDR` — конкретный IP/CIDR monitoring source, которому разрешён `/metrics`.
- `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE` — обязательная private S3-compatible конфигурация. Endpoint обязан быть HTTPS; credentials предоставляют только доступ к выделенному bucket/prefix, без права делать объекты public.
- `EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS=15`, `EXPORT_WORKER_HEARTBEAT_TTL_SECONDS=90` — обязательные production значения Redis heartbeat; interval должен быть меньше TTL.
- `SENTRY_DSN` — опциональный DSN error tracking; пустое значение ничего не отправляет. `SENTRY_ENVIRONMENT=production` можно изменить для изолированного staging. Перед отправкой event удаляются request/user/context, breadcrumbs, custom extras, exception message и stack trace.

При отсутствии/коротком/placeholder JWT, MFA secrets/custodian hashes, development `DATABASE_URL`, включённом seed, insecure cookie, wildcard CORS, не-Redis limiter/resource guard/export queue, private HTTPS S3 configuration или неполном наборе upload/export лимитов production backend аварийно прекращает запуск.

### Reverse proxy и TLS

Готовый production template: [Caddyfile](deployment/caddy/Caddyfile) и [Compose override](deployment/caddy/docker-compose.caddy.yml). Он публикует только `80/443`, перенаправляет HTTP на HTTPS, включает HSTS и пропускает `/metrics` только из `METRICS_ALLOWED_CIDR`. Caddy хранит ACME account/certificates в named volume `caddy_data`; не удаляйте его при обычном restart.

```text
Internet -> Caddy :80/:443 -> frontend Nginx -> backend -> postgres/redis
                  └-> /metrics -> backend (only METRICS_ALLOWED_CIDR)
```

Нельзя публиковать port backend, frontend, PostgreSQL или Redis дополнительно. Caddy по умолчанию игнорирует client-supplied `X-Forwarded-*`, формирует свои header values и передаёт запрос frontend. Frontend добавляет адрес Caddy как следующий hop. Backend запущен с `--no-proxy-headers`; application-level proxy middleware принимает `X-Forwarded-For`/`X-Forwarded-Proto` только когда непосредственный TCP peer входит в `TRUSTED_PROXY_IPS`, затем извлекает первый IP справа, не являющийся trusted proxy. Поэтому запрос клиента напрямую к backend или frontend с поддельным XFF не может сменить ключ login rate-limit.

Перед запуском проверьте конфигурацию без отправки трафика:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

После запуска на реальном domain/infrastructure проверьте redirect `http://<PRACTICEFLOW_DOMAIN>`, HTTPS response и HSTS header. С неразрешённого IP `/metrics` должен вернуть `403`; scrape разрешён только с `METRICS_ALLOWED_CIDR`.

Ограничения: локально можно валидировать syntax/Compose и header-trust behavior, но получение публичного TLS certificate, DNS ownership, доступность портов `80/443`, firewall и реальный monitoring CIDR требуют настоящего домена и публичной infrastructure. Если перед Caddy появится CDN/LB, его CIDR нужно отдельно и осознанно настроить как trusted Caddy upstream; не добавляйте его в `TRUSTED_PROXY_IPS` backend без соответствующей полной proxy chain.

Security headers выставляются и frontend Nginx, и FastAPI. CSP frontend разрешает только same-origin API и `blob:` для защищённых изображений; Swagger CSP отдельно разрешает ресурсы FastAPI CDN.

## Аутентификация и политика паролей

- refresh token находится только в `HttpOnly`, `Secure` production cookie с `SameSite=lax`;
- access token хранится только в памяти вкладки, после reload восстанавливается через cookie rotation;
- frontend API использует `credentials`, backend CORS разрешает credentials только для точных origins;
- refresh привязан к исходной организации и возвращает 401, если membership удалена/деактивирована;
- пароль должен занимать 8–72 UTF-8 байта. Более длинный пароль явно отклоняется при login/create/reset, а не обрезается bcrypt;
- production login rate limit хранится в Redis и разделяется всеми репликами.

## MFA для Director и Super Admin

MFA обязательна для каждого active membership с ролью `DIRECTOR` или `SUPER_ADMIN`. Политика для существующих привилегированных пользователей — **немедленный enrollment**: после корректного пароля сервер выдаёт только одноразовый HttpOnly MFA challenge (TTL 5 минут), а не access/refresh token. Если factor уже есть, challenge требует TOTP; если его ещё нет — требует first-time enrollment. Teacher и Student продолжают использовать существующий flow без изменения API business endpoints.

- TOTP secret хранится только в зашифрованном виде (`MFA_TOTP_ENCRYPTION_KEY`); recovery code хранится только как HMAC hash с отдельным pepper. QR-code/manual key появляются в browser только на enrollment и не логируются.
- После правильного TOTP создаются 10 recovery codes. Они показываются ровно один раз; каждый recovery code одноразовый и приводит к revoke всех сессий и новому enrollment, а не к выдаче токена.
- На challenge действуют TTL, максимум 5 попыток и отдельный Redis-backed MFA rate limit (5 попыток / 10 минут). Password login rate limit остаётся независимым.
- Access и refresh token для privileged membership содержат MFA security version. Reset factor, смена роли/deactivation или password reset отзывает sessions/pending challenges. Password reset не отключает TOTP factor: после reset пароля MFA по-прежнему обязательна.
- При переключении в организацию с privileged membership требуется новый MFA challenge. Tenant context по-прежнему переопределяется по membership в БД на каждом запросе.

### Потеря устройства и Super Admin recovery

Обычный recovery path — сохранённый одноразовый code. Для Super Admin без code доступен peer recovery: password-stage challenge запрашивает подтверждение у другого Super Admin **той же организации**; автор запроса не может подтвердить себя. Подтверждение открывает только новый TOTP enrollment и никогда не создаёт session/token.

Для случая единственного Super Admin имеется двухключевой offline break-glass. Два отдельных custodian вводят свои approvals только в private deployment shell; command сверяет их SHA-256 с production config, отзывает сессии и печатает одноразовый `challenge_id` + enrollment code для secure out-of-band delivery. Это тоже разрешает лишь новый QR enrollment:

```bash
# Run on the deployment host; do not put raw approvals in shell history or .env.
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps \
  -e MFA_BREAK_GLASS_APPROVAL_A -e MFA_BREAK_GLASS_APPROVAL_B \
  backend python scripts/create_mfa_break_glass_challenge.py \
  --user-id <super-admin-user-uuid> --organization-id <organization-uuid>
```

Перед командой deployment operator передаёт `MFA_BREAK_GLASS_APPROVAL_A` и `MFA_BREAK_GLASS_APPROVAL_B` процессу из защищённого механизма secrets/console; command line принимает только UUID. Операцию необходимо документировать по audit log `MFA_BREAK_GLASS_STARTED`, а одноразовый enrollment code передавать отдельным approved channel. Не используйте break-glass как обычный password reset.

Ограничения: это один TOTP factor на user, без WebAuthn/hardware keys и без CRDT-style session sharing. Реальный recovery process также требует организационной процедуры назначения двух custodians; repository не может обеспечить человеческую верификацию или secure out-of-band delivery.

Director может создавать и изменять только Teacher/Student. Изменение, деактивация, смена роли, invite и password reset для Director/Super Admin доступны только Super Admin текущей организации.

## API эксплуатация

- list-endpoints поддерживают `offset` (от 0) и `limit` (1–200, default 50), сохраняя прежний JSON-массив в response для обратной совместимости;
- метаданные страницы передаются в `X-Total-Count`, `X-Has-More`, `X-Offset` и `X-Limit` (они доступны browser-клиенту через CORS `Access-Control-Expose-Headers`);
- порядок коллекций стабилен: все сортировки имеют уникальный tie-breaker. `GET /management/members?q=` и `GET /groups/{group_id}/available-students?q=` выполняют ограниченный по длине серверный поиск по имени/email только после tenant scope;
- каждый response содержит `X-Request-ID`; валидный входной ID переиспользуется, иначе генерируется UUID;
- HTTP access logs имеют JSON-формат;
- `/health/live` проверяет процесс, `/health/ready` — PostgreSQL, login rate-limit, resource-protection backend, export queue и configured storage backend;
- `/metrics` отдаёт безопасные Prometheus metrics: HTTP count/status class/latency histogram/in-flight, SQLAlchemy pool capacity/occupancy и DB errors, Redis used/max memory, dependency state, storage/Redis failures, MFA results, export lifecycle/queue/worker heartbeat, quota/rate-limit blocks и aggregate storage usage. Labels — только method, route template, status class, component, operation, result, format/status и fixed reason; там нет user/organization ID, email, token, filename, object key, document content или raw URL.

## Observability production

`/metrics` остаётся закрыт существующим Caddy ACL `METRICS_ALLOWED_CIDR`; не публикуйте backend port и не обходите Caddy для scrape. Сам endpoint не требует application token, поэтому доступ к нему должен оставаться только в private monitoring network. HTTP logs содержат irreversible SHA-256 fingerprint `X-Request-ID` (а не потенциально client-supplied value); worker log event содержит безопасный `export_job_id` correlation field. Логи пишут route template и exception type, но не raw URL/path или exception text.

`export-worker` публикует Redis heartbeat с interval/TTL из production env. Его monitoring signal: `practiceflow_export_worker_heartbeat_age_seconds`, `practiceflow_export_worker_active`; backend endpoint `GET /health/worker/export` даёт `503`, если heartbeat отсутствует/stale. Это endpoint для internal monitoring, не замена proxy ACL.

Готовые assets: [alert rules](deployment/observability/prometheus-alerts.yml), [minimal Grafana dashboard](deployment/observability/practiceflow-dashboard.json), [runbook](deployment/observability/RUNBOOK.md) и [capacity planning](docs/CAPACITY_PLANNING.md). Исходные thresholds включают 5xx >2% 10m, p95 >1.5s 10m, dependency unavailable >2m, pool/Redis memory >80% 5m, queue >10 10m, heartbeat stale >90s, storage errors, >5 export failure/timeout 15m и >20 limit blocks 10m. CPU/RAM rules требуют уже существующий cAdvisor-compatible Docker collector и до включения должны быть сверены с его labels. После первого soak/capacity test настройте все thresholds под реальную нагрузку.

Sentry необязателен: без `SENTRY_DSN` backend/worker продолжают работать без SDK network traffic. При включении SDK получает только sanitized event; DSN сам является secret и не должен попадать в source control или logs. Prometheus/Grafana/Sentry account и monitoring network не создаются этим repository — deployer подключает их отдельно.

## Production audit trail

`audit_logs` is an application-level append-only investigation trail. Every new tenant-scoped event receives an increasing `sequence`, the preceding event hash and an `event_hash = SHA-256(canonical immutable payload)`. The payload contains only tenant/actor/target UUIDs, action, timestamp, safe bounded operational metadata and HMAC fingerprints of the request ID, export correlation ID and client IP. It never stores passwords, JWT/refresh/access-link tokens, MFA secrets/recovery codes, document contents, file names, email or free-form personal text.

The API exposes read-only `GET /api/v1/audit-events` and `GET /api/v1/audit-events/integrity` to a **Super Admin of the currently selected organization only**. There is no organization selector: tenant scope is derived from the validated membership on every request. Both viewing and integrity verification append their own audit event. The collection keeps its array response and exposes `X-Total-Count`, `X-Has-More`, `X-Offset` and `X-Limit`; supported filters are `from`, `to`, `action`, `actor_id`, `target_type`, `target_id`.

Set these production variables explicitly:

- `AUDIT_HASH_PEPPER` — independent random secret of at least 32 bytes for HMAC fingerprints. Do not reuse JWT/MFA/recovery secrets and do not rotate it without a planned correlation-window transition.
- `AUDIT_RETENTION_DAYS=365` — retention period for events. Confirm this meets local legal and investigation requirements before deployment.
- `AUDIT_CLEANUP_INTERVAL_SECONDS=21600` — how often the deployed export worker performs retention cleanup.

Before deleting expired tenant rows, cleanup appends `AUDIT_RETENTION_CHECKPOINT` and saves the hash/sequence of the last deleted entry as that tenant's retention anchor. Integrity verification resumes from the anchor, so pruning cannot masquerade as an unbroken full-history chain. A failed cleanup transaction removes neither its intended rows nor the anchor update. Keep the export worker running; otherwise retention is intentionally not executed in-process by API replicas.

Hash chaining detects accidental or ordinary application/API-level alteration, missing rows and reordered events. It does **not** make a normal PostgreSQL table immutable to a database superuser who can rewrite rows and chain heads. For stronger external immutability, optionally copy canonical events/checkpoints to a separately controlled audit sink, or a private S3 bucket with Object Lock (compliance/WORM mode), versioning, separate retention governance and cross-account access. This repository does not enable an external provider or claim WORM protection; any such integration needs a tested, access-controlled deployment design.

## Optimistic locking документов

Рабочий draft отчёта (`reports`) и редактируемая версия шаблона (`template_versions`) имеют независимое целочисленное поле `revision`. Миграция `a6b7c8d9e0f1` инициализирует существующие документы значением `1`; каждая успешная запись увеличивает его на единицу.

`GET /api/v1/reports/{report_id}/document` и `GET /api/v1/templates/{template_id}/versions/{version_id}/document` возвращают актуальный `revision`. PATCH обязан передать значение, на основе которого пользователь редактировал данные:

```json
// report
{ "expected_revision": 7, "sections": { "section-id": [] } }

// template version
{ "expected_revision": 7, "document": { "schema_version": 1, "meta": {}, "sections": [] } }
```

Запись выполняется compare-and-swap: SQL обновляет строку только при совпадении ожидаемой revision и одновременно повышает её. При устаревшем значении API отвечает `409` с `detail.code = "STALE_DOCUMENT_REVISION"`, не изменяя document data. Редакторы останавливают очередь автосохранения, блокируют дальнейшее редактирование и предлагают скопировать локальный черновик либо загрузить актуальные данные. Это не заменяет CRDT или совместное редактирование в реальном времени.

## Backup и restore

`backup-postgres.ps1` и `backup-postgres.sh` сохранены как совместимые точки входа для **LocalStorage**. Они создают единый bundle, а не только PostgreSQL dump. Bundle имеет вид `practiceflow-backup-YYYYMMDDTHHMMSSZ/` и содержит:

- `database.dump` — сжатый PostgreSQL custom-format dump;
- `backend-storage.tar.gz` — архив persistent named volume `backend_storage` с загруженными изображениями;
- `manifest.json` — UTC-дата, перечень артефактов, размер и SHA-256 каждого;
- `manifest.sha256` — checksum самого manifest.

Для согласованности LocalStorage script на короткое время останавливает `backend` (только если он был запущен), затем снимает DB dump и storage archive, удаляет временный helper container и запускает backend обратно. Планируйте это как короткое maintenance window: в проекте нет режима read-only, поэтому online snapshot не может гарантировать согласованность между двумя independent volumes.

### S3 object-storage backup и restore

Production Compose использует S3, поэтому archive `backend_storage` не является backup-ом production objects. Настройте у провайдера bucket до первого upload:

- bucket block-public-access и отсутствие public ACL/policy; приложение не выдаёт public/presigned URL;
- versioning с отдельно утверждённой lifecycle/retention policy, достаточной для `EXPORT_JOB_RETENTION_SECONDS` и recovery window;
- replication в отдельный account/region либо другой off-site immutable backup target; replication не заменяет PostgreSQL dump;
- мониторинг replication lag, failed lifecycle rules и доступа к bucket.

Восстановление S3 выполняется только как disaster-recovery procedure в изолированном target: восстановите PostgreSQL dump и согласованный snapshot/version objects в private target bucket, настройте backend и worker на этот bucket, затем проверьте `/health/ready`, authorized image API, открытие report с image и новый DOCX/PDF export. Не делайте restore поверх live bucket: ключи намеренно стабильны, и смешивание версий DB/object storage может выдать неверный artifact или потерять данные. Репозиторий не запускает provider restore и не создаёт external bucket автоматически — это требует доступа deployer-а к реальной S3 infrastructure.

Windows:

```powershell
.\scripts\backup-postgres.ps1 -OutputDirectory .\backups -ComposeFile docker-compose.prod.yml -EnvFile .env.production
```

Linux/macOS:

```bash
chmod +x scripts/backup-postgres.sh
ENV_FILE=.env.production COMPOSE_FILE=docker-compose.prod.yml ./scripts/backup-postgres.sh ./backups
```

### Безопасный restore

Restore разрешён только в **пустую** target database и пустой `backend_storage`; скрипт проверяет оба условия и не допускает restore в существующую application schema. До записи данных он сверяет SHA-256 самого manifest и каждого артефакта, а также размеры артефактов.

1. Создайте отдельный Compose project и отдельный пустой volume/database. Не используйте running production project как target.
2. Соберите backend image, но поднимите до restore только PostgreSQL:

```bash
RESTORE_PROJECT="pf-restore-$(date +%s)-$$"
docker compose --project-name "$RESTORE_PROJECT" --env-file .env.restore -f docker-compose.prod.yml build backend
docker compose --project-name "$RESTORE_PROJECT" --env-file .env.restore -f docker-compose.prod.yml up -d --wait postgres
ENV_FILE=.env.restore COMPOSE_PROJECT_NAME="$RESTORE_PROJECT" COMPOSE_FILE=docker-compose.prod.yml \
  ./scripts/restore-practiceflow.sh ./backups/practiceflow-backup-YYYYMMDDTHHMMSSZ --confirm-empty-target
docker compose --project-name "$RESTORE_PROJECT" --env-file .env.restore -f docker-compose.prod.yml up -d --wait backend
```

Windows PowerShell:

```powershell
$restoreProject = "pf-restore-$([guid]::NewGuid().ToString('N').Substring(0,12))"
docker compose --project-name $restoreProject --env-file .env.restore -f docker-compose.prod.yml build backend
docker compose --project-name $restoreProject --env-file .env.restore -f docker-compose.prod.yml up -d --wait postgres
.\scripts\restore-practiceflow.ps1 -BackupDirectory .\backups\practiceflow-backup-YYYYMMDDTHHMMSSZ -ConfirmEmptyTarget -ProjectName $restoreProject -EnvFile .env.restore
docker compose --project-name $restoreProject --env-file .env.restore -f docker-compose.prod.yml up -d --wait backend
```

`--clean` используется только внутри уже проверенного пустого target, никогда не применяйте restore script к live production project. После restore проверьте `/health/ready`, вход пользователя, открытие документа с изображением и DOCX/PDF export.

Если restore завершился ошибкой после начала записи, не запускайте его повторно на том же target: удалите только этот отдельный disposable project вместе с его volumes, создайте новый пустой target и повторите restore. Скрипт намеренно не пытается автоматически очищать частично восстановленные данные.

### Проверка backup/restore цепочки

`scripts/verify-backup-restore.py` поднимает две изолированные disposable Compose среды с разными project names и volumes. Сценарий выполняет реальный upload PNG через API, добавляет его в student report, создаёт bundle, восстанавливает его в чистую среду и проверяет file endpoint, document reference и DOCX export с embedded image.

```bash
python scripts/verify-backup-restore.py
```

Скрипт в конце удаляет только свои явно именованные temporary Compose projects `practiceflow_backup_verify_source` и `practiceflow_backup_verify_restore` вместе с их volumes.

## CI

`.github/workflows/ci.yml` выполняет:

- backend Ruff, MyPy для security/operations layers, полный pytest;
- `alembic upgrade head` и `alembic check` на отдельной PostgreSQL;
- frontend lint, tests и production build;
- `pip-audit` и `npm audit --audit-level=high`.
- Markdown links и обязательный набор production runbooks.
- после успешных backend/frontend jobs — `E2E integration`: собирает PostgreSQL, Redis, private MinIO bucket, backend/worker и frontend Nginx из `docker-compose.e2e.yml`, затем запускает весь Playwright regression suite против `http://127.0.0.1:4173`.

Job не использует GitHub Secrets, production database, persistent volumes или внешний network ingress. Для настоящего merge-gate администратор репозитория должен включить required status check **`CI / E2E integration`** в branch protection/ruleset целевой ветки: GitHub Actions workflow может публиковать этот check, но не может сам изменить repository policy.

`Supply chain security` отдельно закрепляет Docker base/service images и
GitHub Actions на immutable SHA, собирает production backend/frontend images,
генерирует SPDX SBOM и блокирует High/Critical CVE в Trivy (кроме временно
документированных CVE exceptions). Он публикует SBOM, scan reports и JUnit test
reports как artifacts, не публикуя image и не читая deployment secrets.
Добавьте **`Supply chain security / Build, attest and scan production images`**
в required checks. Полный порядок обновления digest, локальной генерации и
проверки SBOM, CVE exception и keyless Cosign/OIDC release signature описан в
[Supply-chain security guide](docs/SUPPLY_CHAIN_SECURITY.md).

## Хранилище файлов

Все файлы проходят через `StorageService`. `LocalStorageService` остаётся default для development, pytest и volume backup/restore. Production принудительно использует `S3StorageService` (AWS S3 или private compatible endpoint); backend и `export-worker` используют одинаковые server-generated keys (`orgs/<organization UUID>/images|exports/<object UUID>`), поэтому replica не зависит от локального filesystem. Key никогда не строится из filename и дополнительно rejects path traversal.

Image upload читает поток кусками, декодирует и проверяет реальные PNG/JPEG/WebP bytes через Pillow, отклоняет повреждённые данные и несовпадение заявленного MIME. S3 upload читает staged stream, не публикует bucket/object и не устанавливает ACL. Записи и выдача файлов tenant-scoped; frontend получает изображения и export artifacts только через авторизованный API, который повторно проверяет organization и права исходного report. Недоступный S3 backend не bypass-ится: readiness становится `503`, upload/download отвечают `503` без деталей provider-а.

### Перенос LocalStorage в S3

Отдельный copy-only tool `backend/scripts/migrate_local_storage_to_s3.py` переносит только objects, на которые есть ссылки в `files` и succeeded `export_jobs`; схема БД и API не меняются, потому что existing storage keys сохраняются. Он рассчитывает size и SHA-256 source, поддерживает `--dry-run`, при повторе пропускает уже совпадающий S3 object, а при checksum mismatch **не перезаписывает** destination. Local source никогда не удаляется автоматически; результат всегда пишется в JSON report с `transferred`, `skipped`, `would_transfer` и `errors`.

Сначала сделайте проверенный LocalStorage backup, создайте private target bucket/versioning и предоставьте deployment credential. Выполняйте реальную копию в maintenance window (остановите backend и export-worker либо исключите cleanup/uploads), чтобы database metadata и набор objects не менялись во время сверки. Пример запуска из image с legacy volume, где `<backend-image>` и Docker network выбирает deployer:

```bash
# S3_* and DATABASE_URL are supplied through a protected env file; source is read-only.
docker run --rm --env-file .env.s3-migration \
  --network <deployment-network> \
  -v <legacy-backend_storage-volume>:/source:ro \
  -v "$PWD/migration-reports:/reports" \
  <backend-image> python scripts/migrate_local_storage_to_s3.py \
  --local-root /source --dry-run --report /reports/dry-run.json

# Review dry-run.json first; only then run without --dry-run.
```

The command never runs automatically during deployment and this repository does not run it against real data.

## Лимиты upload и export

Development использует потокобезопасный in-memory guard с безопасными default значениями. Production запускается только с `RESOURCE_GUARD_BACKEND=redis`: недоступный Redis не отключает защиту, а возвращает `503` до upload/export. Все production values должны быть явно заданы в `.env.production`; Compose и backend откажутся запускаться с пропуском.

Рекомендуемая исходная конфигурация (см. `.env.production.example`) рассчитана на небольшую организацию:

- `UPLOAD_MAX_FILE_BYTES=5242880` — максимум одного изображения (5 MiB); превышение — `413`.
- `UPLOAD_RATE_LIMIT_REQUESTS=20`, `UPLOAD_RATE_LIMIT_WINDOW_SECONDS=60` — частота upload на membership в организации.
- `UPLOAD_USER_MAX_FILES=100`, `UPLOAD_USER_MAX_BYTES=104857600`, `UPLOAD_USER_QUOTA_WINDOW_SECONDS=86400` — количество и объём принятых изображений одной membership за 24 часа.
- `UPLOAD_ORGANIZATION_MAX_STORAGE_BYTES=5368709120` — 5 GiB persistent images на организацию. Сервис берёт фактическую сумму только по `files.organization_id` текущей организации и добавляет Redis reservation ещё не сохранённых файлов в одной атомарной операции.
- `UPLOAD_RESERVATION_TTL_SECONDS=900` — fail-closed срок reservation при crash процесса; `UPLOAD_QUOTA_RETRY_AFTER_SECONDS=60` — retry hint при storage quota.
- `EXPORT_USER_RATE_LIMIT_REQUESTS=10`, `EXPORT_ORGANIZATION_RATE_LIMIT_REQUESTS=60`, `EXPORT_RATE_LIMIT_WINDOW_SECONDS=60` — rate limits DOCX/PDF на user и organization.
- `EXPORT_MAX_CONCURRENT_PER_USER=1`, `EXPORT_MAX_CONCURRENT_PER_ORGANIZATION=3` — slots захватываются только worker перед рендером, а не HTTP API.
- `EXPORT_TIMEOUT_SECONDS=45` — TTL resource-guard slot; `EXPORT_WORKER_HARD_TIMEOUT_SECONDS=45` — wall-clock deadline renderer child; `EXPORT_WORKER_LEASE_SECONDS=75` — restart lease (не меньше hard timeout).
- `EXPORT_JOB_RETENTION_SECONDS=86400` — хранить готовый artifact и job result 24 часа; `EXPORT_WORKER_QUEUE_TIMEOUT_SECONDS=5`, `EXPORT_WORKER_REQUEUE_DELAY_SECONDS=1` — polling Redis worker и задержка при занятых slots.

Счётчики Redis именуются tenant-scoped (`organization_id + user_id`); org storage reservation не содержит filename, document или данные другой организации. Redis Lua operations атомарно резервируют user quota, org quota и worker export slots, поэтому параллельные worker не могут пройти через проверку одновременно. При `429` backend добавляет `Retry-After`: frontend показывает понятное сообщение; кнопка export не создаёт повторные jobs, пока активная job готовится.

### Асинхронная проверка готовых DOCX

Преподавателю также доступен раздел **Группы проверки**: загрузка курсовых и
отчётов по группам без студенческих аккаунтов, замечания, отдельное завершение
преподавательской проверки и общая сводка нарушений по закреплённым запускам.
Для обновления нужна новая миграция `4c5d6e7f8091` (`alembic upgrade head`).
Сценарий, API и правила расчёта описаны в
[Группах проверки преподавателя](docs/TEACHER_REVIEW_GROUPS.md).

Раздел проверки документов доступен только преподавателю. Преподаватель сам
выбирает опубликованную версию профиля, при необходимости указывает имя
студента или название работы и загружает готовый `.docx`. Аккаунт студента,
группа и назначение для этого не требуются. Принятый оригинал сохраняется
неизменяемым и создаёт `DocumentCheckJob` в PostgreSQL. Отдельный
`document-check-worker` забирает задания через `FOR UPDATE SKIP LOCKED`, повторно
проверяет размер и SHA-256 неизменяемого оригинала и запускает разбор OOXML в
дочернем процессе с жёстким таймаутом. В Phase 2.2 выполняются правила формата
страницы и полей, шрифтов и размеров, интервалов и отступов. Остальные типы
правил явно учитываются как пропущенные, поэтому интерфейс не выдаёт их за
выполненные.

Результат содержит только структурные координаты и ожидаемые/обнаруженные
параметры без текста документа. Историю, результаты и оригинал видит только тот
преподаватель, который загрузил файл, внутри своей текущей организации.
Студенческие маршруты проверки скрыты из интерфейса и OpenAPI и по умолчанию
возвращают `404`; совместимость включается только явной настройкой
`DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED=true`. Оригинал не изменяется;
автоматическая оценка и исправленный DOCX/PDF не создаются.

Параметры `DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS`,
`DOCUMENT_CHECK_WORKER_LEASE_SECONDS`, `DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS`,
`DOCUMENT_CHECK_WORKER_POLL_SECONDS` и `DOCUMENT_CHECK_MAX_FINDINGS` задаются в
окружении. Lease должен быть больше таймаута. Compose автоматически поднимает
worker и проверяет его доступ к PostgreSQL и private storage.

### Асинхронный DOCX/PDF export

`POST /api/v1/reports/{report_id}/exports/{docx|pdf}` возвращает `202` и `{job_id, status}`. Повторная отправка того же report+format, пока job имеет `queued` или `running`, возвращает тот же `job_id`: partial unique index PostgreSQL делает это атомарным между API replicas. UI опрашивает `GET /api/v1/export-jobs/{job_id}` и скачивает только `GET /api/v1/export-jobs/{job_id}/download` после `succeeded`; `DELETE /api/v1/export-jobs/{job_id}` отменяет queued job либо запрашивает остановку running renderer.

`export-worker` читает Redis queue, но PostgreSQL `export_jobs` — источник истины. При restart он переотправляет queued и expired-lease running jobs; дубли Redis безвредны, потому что worker atomically claim-ит только `queued`. Каждый renderer запускается отдельным child process. По cancel или `EXPORT_WORKER_HARD_TIMEOUT_SECONDS` parent принудительно `terminate`/`kill`-ит child **до** terminal status и всегда освобождает Redis slot. Success/error/timeout/cancel сохраняются соответственно как `succeeded`/`failed`/`timed_out`/`cancelled`; cleanup удаляет локальный artifact и terminal ledger после `EXPORT_JOB_RETENTION_SECONDS`.

Artifact лежит через `StorageService` под private `orgs/{organization_id}/exports/...` в LocalStorage или S3/MinIO. Status и download повторно проверяют текущий tenant-scoped доступ к исходному report, а worker повторно проверяет active membership, user и role/profile перед рендером. Таким образом готовый файл не становится обходом RBAC после удаления из группы/организации.

`docker compose ... up -d --build` поднимает `export-worker` автоматически. Его healthcheck проверяет PostgreSQL, Redis queue и Redis resource guard. Реальный production rollout всё ещё требует Redis/worker soak test на worst-case DOCX/PDF, CPU/RAM limits и наблюдения за cleanup: этот репозиторий не может проверить длительную нагрузку или crash host/infrastructure вместо container process.
