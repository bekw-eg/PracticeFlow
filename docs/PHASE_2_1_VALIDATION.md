# PracticeFlow — Phase 2.1

Дата проверки: 2026-09-07. Реализация добавлена поверх незакоммиченных Phase 1/1.5.
Старые миграции и legacy editor, templates, reports, comments, export worker сохранены.
`LEGACY_DOCUMENT_EDITOR_ENABLED` по умолчанию остаётся `true`.

## Реализовано

- `StudentDocumentSubmission`: точные assignment/snapshot/student, номер попытки,
  нормализованное имя, закрытый ключ оригинала, размер, SHA-256, фактический DOCX MIME,
  время отправки, late marker, ключ идемпотентности и версия preflight.
- `DocumentCheckJob`: tenant/submission, QUEUED/PROCESSING/COMPLETED/FAILED,
  временные отметки и безопасные поля ошибки. При приёме создаётся ровно один QUEUED job.
- Одна миграция `ea2f3a4b5c6d` поверх `da1e2f3a4b5c`.
- Student UI: навигация, назначения, загрузка DOCX, новая попытка, история,
  late marker, статус job, скачивание оригинала; сохранение ключа при повторе запроса.
- Teacher UI: snapshot студентов, все попытки с пагинацией и фильтром по студенту,
  скачивание оригиналов. Переводы ru/kk/en и feature flags из `/auth/me`.

## API

Ниже пути относительно `/api/v1/document-checks`:

| Метод | Путь | Доступ |
| --- | --- | --- |
| GET | `/student/assignments` | Студент из snapshot; опубликованные и закрытые для истории |
| GET | `/student/assignments/{assignment_id}` | Назначенный студент |
| GET | `/student/assignments/{assignment_id}/submissions` | Собственные попытки |
| POST | `/student/assignments/{assignment_id}/submissions` | Multipart `file`, обязательный `Idempotency-Key` |
| GET | `/assignments/{assignment_id}/submissions` | Преподаватель текущей группы; необязательный `student_id` |
| GET | `/submissions/{submission_id}/original` | Владелец-студент или преподаватель группы |

Новая попытка возвращает 201, идентичный повтор — 200 и существующий job.
Иное содержимое/нормализованное имя с тем же ключом возвращает 409.
Новая загрузка разрешена только для PUBLISHED; поздняя отправка помечается `is_late`.
Повтор уже принятого запроса после закрытия не создаёт новую попытку.
Списки используют offset/limit и существующие `X-Total-Count`/`X-Has-More` headers.
Другой tenant или недоступный объект возвращает 404; неправильная роль — общий 403.
Ключи хранилища и публичные URL в ответах отсутствуют.

## Неизменяемость и безопасность

- PostgreSQL composite FK связывают tenant, assignment, snapshot и student.
  Блокировки assignment/snapshot сериализуют приём и номера попыток; unique constraints
  защищают номер, ключ идемпотентности, ключ хранилища и единственность job.
- UPDATE/DELETE оригинала запрещены триггером, включая прямой SQL; ORM также запрещает
  изменение. Deferred constraint требует job до завершения транзакции. Identity job
  нельзя перепривязать или удалить.
- Local storage создаёт файл эксклюзивно; S3 использует `If-None-Match: *`.
  Ключ строится сервером из UUID tenant/assignment/student/submission и SHA-256.
  Скачивание проходит через авторизованный backend с безопасным Content-Disposition.
- Исходные байты не преобразуются. Потоковая подготовка использует временный файл;
  ограничения действуют также до разбора multipart, включая chunked requests.
- Блокируются DOCM, VBA payload, macro-enabled content types, OLE/password-protected
  Office, encrypted ZIP flags, traversal/absolute paths, symlinks, duplicate entries,
  превышение числа entries/распакованных размеров/compression ratio, повреждённые ZIP/XML,
  отсутствие обязательных OOXML частей, DTD/entities и неверный тип main document.
- Работают общие rate limits, user quotas и tenant quotas с учётом старых File и новых originals.
  При обычной ошибке БД удаляется только новый orphan; при конфликте записи предыдущий
  объект остаётся нетронутым. Отдельный S3 write marker защищает очистку после потери ответа PUT.
- Audit фиксирует приём, создание job, скачивание каждым типом пользователя и отклонение
  вредоносного DOCX без содержимого, имени, полного ключа или внутренних исключений.

## Результаты проверок

| Проверка | Результат |
| --- | --- |
| PostgreSQL | Реальная изолированная PostgreSQL 18.3, порт 55432; Docker daemon недоступен |
| Alembic | Upgrade с пустой БД до head; downgrade только новой миграции и повторный upgrade — успешно |
| Новые тесты | 44 API/DB проверки и 42 независимые проверки DOCX/storage/multipart проходят |
| Финальный связанный backend набор | **121 passed**: Phase 1, Phase 2.1, feature flags, tenant isolation, S3/storage migration, observability, unit tests |
| Полный backend suite | **313 passed, 2 failed, 2 skipped**; причины ниже |
| Backend lint / compilation | Ruff и compileall проходят |
| Type checks | MyPy security/operations и нового middleware: 15 файлов, без ошибок |
| OpenAPI | 3.1.0, 95 путей; Pydantic OpenAPI validation, разрешение `$ref`, уникальность operation IDs проходят |
| Frontend tests | **187 passed**, 33 файла |
| Frontend build / lint | Успешно; Vite сообщает о существующем крупном JS bundle |
| Live S3/MinIO | Требует недоступного Docker/MinIO; выполняемые без него тесты адаптера проходят |

Полный backend прогон включал 41 независимый unit test. Затем добавлен ещё один тест
очистки S3 после потерянного подтверждения PUT; финальные 42 unit tests входят в набор 121.

Ошибки полного набора относятся к старому PDF-экспорту:

- `test_export.py::TestPdfExport::test_export_produces_valid_pdf_with_expected_text`;
- `test_export.py::TestPdfExport::test_export_audit_logged`.

Обе ошибки: WeasyPrint не может загрузить `libgobject-2.0-0` в локальном Windows runtime.
Два пропуска — визуальные PDF/DOCX glyph regressions: отсутствуют доступный native renderer
и LibreOffice. Новые PostgreSQL-тесты не пропущены. Старый код экспорта не менялся ради
обхода этих проверок. Live MinIO tests запускаются отдельным integration gate.

Схема: [phase21-openapi.json](../outputs/phase21-openapi.json).
Журналы и JUnit: [outputs/phase21-validation](../outputs/phase21-validation).

## Файлы Phase 2.1

Пути ниже описывают эту фазу, а не весь существовавший до неё пользовательский diff.

- `backend/alembic/versions/ea2f3a4b5c6d_immutable_docx_submissions.py`.
- `backend/app/models/{document_check.py,enums.py,__init__.py}`.
- `backend/app/schemas/document_check.py`, `backend/app/api/v1/document_checks.py`.
- `backend/app/services/{document_submission_service.py,docx_preflight.py,submission_storage.py}`.
- `backend/app/storage/{base.py,local.py,s3.py}`.
- `backend/app/repositories/file_repository.py`, `backend/app/resource_protection.py`.
- `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/document_submission_limits.py`.
- `backend/app/tests/test_document_check_phase21.py`.
- `backend/unit_tests/{test_docx_preflight.py,test_submission_storage.py,test_document_submission_limits.py}`.
- `backend/app/s3_integration_tests/test_minio_storage.py`, `.github/workflows/ci.yml`.
- `frontend/src/App.tsx`, `frontend/src/app/AppShell.tsx`, `frontend/src/types/api.ts`.
- `frontend/src/features/documentChecks/{StudentCheckAssignmentsPage.tsx,StudentCheckAssignmentPage.tsx,SubmissionHistory.tsx,TeacherSubmissionPanel.tsx,submissionApi.ts,Submissions.test.tsx,CheckAssignmentDetailPage.tsx}`.
- `frontend/src/lib/apiError.ts`, `frontend/src/i18n/locales/{ru.ts,kk.ts,en.ts}`, `frontend/nginx.conf`.
- `.env.example`, `.env.production.example`, `docker-compose.yml`, `docker-compose.prod.yml`.
- `docs/ARCHITECTURE.md`, `docs/ROLE_MATRIX.md`, этот отчёт и результаты в `outputs`.

## Границы этапа

Analyzer не подключён: jobs остаются QUEUED. Findings, annotated DOCX/PDF,
автоматическая оценка и teacher grading отсутствуют. Оригинал не исправляется.
Export queue/worker для этих jobs не используются.

При длительной недоступности БД/S3 после неоднозначного завершения операции невозможно
доказать отсутствие владельца объекта. В этом случае объект сохраняется консервативно;
необходимость последующей orphan reconciliation явно описана в ARCHITECTURE.md.
Не заявляется распределённая транзакция между PostgreSQL и object storage.

При изменении DOCX upload limit необходимо согласовать nginx ceiling (сейчас 21 MiB)
с backend limit и multipart overhead.
