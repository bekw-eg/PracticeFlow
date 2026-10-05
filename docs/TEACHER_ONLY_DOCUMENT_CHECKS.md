# Проверка teacher-only загрузки готовых DOCX

Дата проверки: 8 сентября 2026 года.

Это исторический отчёт. Изменения от 15 сентября — настройки отдельных
документов, заголовки и повторные запуски — описаны в
[Правилах документа и повторных проверках](DOCUMENT_RULES_AND_RECHECKS.md).
Приведённые ниже результаты тестов к новой функции не относятся.

Требования к оцениванию оригинала и запрету выдачи студенту готовой исправленной
работы описаны в [Политике оценивания документов](DOCUMENT_ASSESSMENT_POLICY.md).

## Итоговое поведение

- Раздел проверки документов доступен в интерфейсе только роли `TEACHER`.
- После входа преподаватель сразу попадает в раздел прямой проверки; он также
  расположен первым в боковом меню.
- Преподаватель выбирает опубликованную версию профиля и загружает готовый
  `.docx` напрямую. Аккаунт студента, группа, roster snapshot и назначение не
  требуются. Необязательное поле `student_label` позволяет подписать работу.
- Каждая принятая загрузка создаёт неизменяемый
  `TeacherDocumentSubmission`, приватный оригинал и ровно один
  `DocumentCheckJob` в состоянии `QUEUED`.
- Worker повторно проверяет размер и SHA-256, запускает существующий анализатор
  Phase 2.2 и сохраняет структурированные замечания без текста документа.
- Пока job находится в `QUEUED` или `PROCESSING`, история автоматически
  обновляется и показывает готовый результат без ручной перезагрузки страницы.
- История, результаты и скачивание оригинала требуют текущую организацию и
  точный `teacher_id` владельца. Идентификаторы другой организации или другого
  преподавателя не раскрываются и возвращают `404`.
- Студенческая навигация и маршруты интерфейса удалены. Исторические API
  загрузки студента скрыты из OpenAPI и по умолчанию возвращают `404` через
  `DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED=false`.

## Публичный API

Все маршруты ниже требуют роль `TEACHER`:

- `GET/POST /api/v1/document-checks/teacher/submissions`;
- `GET /api/v1/document-checks/teacher/submissions/{submission_id}`;
- `GET /api/v1/document-checks/teacher/submissions/{submission_id}/original`;
- `GET /api/v1/document-checks/teacher/submissions/{submission_id}/findings`.

`POST` использует `multipart/form-data`, обязательные `file`,
`profile_version_id` и заголовок `Idempotency-Key`, а также необязательный
`student_label`. Повтор с тем же ключом и теми же данными возвращает принятую
запись; повторное использование ключа для других данных возвращает `409`.
Storage key и `teacher_id` не публикуются в ответе.

## Защита данных

- Ограничитель полного multipart-тела применяется и к teacher-only маршруту.
- DOCX проходит ограниченную проверку ZIP/OOXML до записи в private storage.
- Ключ хранения включает организацию, преподавателя, submission ID и SHA-256;
  существующий объект не перезаписывается.
- PostgreSQL связывает submission с организацией и точной версией профиля,
  требует опубликованное состояние, проверяет принадлежность преподавателя
  tenant-у и запрещает изменение или удаление принятой записи.
- `DocumentCheckJob` ссылается ровно на один источник: историческую student
  submission или новую teacher submission. Deferred trigger требует ровно одну
  job для каждой teacher submission.
- Квота хранилища и метрика общего объёма учитывают оба типа оригиналов.

## Результаты проверки

| Проверка | Результат |
| --- | --- |
| Сценарии интерфейса проверки документов | **23 passed** |
| Полный frontend-набор | **192 passed** |
| Связанный backend-набор профилей, DOCX, очереди, лимитов и feature flags | **119 passed** |
| Полный backend application-набор | **278 passed, 2 skipped, 2 ошибки окружения** |
| Миграции PostgreSQL | upgrade до `0c4d5e6f7a8b`, downgrade до `fb3a4b5c6d7e`, повторный upgrade и `alembic check` пройдены |
| Публичная OpenAPI-схема | содержит только четыре teacher submission route; student route отсутствует |
| Статический анализ и сборка | Ruff, Python compileall, frontend lint и production build пройдены |
| Docker Compose | development, E2E и production конфигурации проходят `config` validation |

Две ошибки полного backend-набора относятся к существующему PDF-экспорту:
локальная Windows-среда не содержит нативные библиотеки Pango/Cairo для
WeasyPrint. Связанные тесты DOCX и все новые teacher-only сценарии прошли.
## Original lifecycle and preview boundaries

The teacher can archive a submission without changing its immutable upload or
completed check history. The separate lifecycle record also controls whether
source details may be disclosed to other teachers. Removing the original DOCX
is a two-phase, retryable operation: the request is recorded before storage is
called, and the quota is released only after storage confirms deletion. Active
checks block removal; pending removal is shown to the owner and can be retried.

The private HTML preview now preserves paragraph anchors through nested tables,
merged cells, Word list labels and safe raster image embeds. External image
relationships, SVG and active content are excluded. Browser pagination remains
a measured approximation of Word layout, so very large or unusual constructs
may be scaled or split at the nearest safe table/paragraph boundary.
