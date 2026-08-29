# PracticeFlow — QA Regression Report

**Дата:** 2026-08-27  
**Среда:** Docker development stack, `http://localhost:5173`  
**Production readiness:** **90/100**

## Исправленные дефекты

### BUG-001 — student получает ложный 403 при открытии редактора отчёта

**Status:** **FIXED + VERIFIED**

`ReportEditorPage` больше не запрашивает teacher-only `/api/v1/variables/catalog`. Каталог остаётся в `TemplateEditorPage`, где он нужен преподавателю для работы с шаблонами. В student report editor скрыт недоступный control «Вставить переменную».

**Verification:** Playwright выполнил реальный flow `student login → Мои отчёты → Требует доработки → Редактировать` и подтвердил, что:

- страница и редакторы открываются;
- не было запросов к `/api/v1/variables/catalog`;
- не было 403 и toast `This action requires one of: ['TEACHER']`;
- после успешного login не было console errors.

### BUG-002 — rich-text editors не имеют accessible name

**Status:** **FIXED + VERIFIED**

Tiptap/ProseMirror surface теперь получает `role="textbox"`, `aria-multiline="true"` и уникальный `aria-label` вида `Редактор раздела: <название>`. Имя синхронизируется при изменении названия раздела.

**Verification:** unit test и Playwright обнаружили уникальные editors:

- `Редактор раздела: Введение`;
- `Редактор раздела: Глава 1`;
- `Редактор раздела: Глава 2`;
- `Редактор раздела: Глава 3`;
- `Редактор раздела: Заключение`;
- `Редактор раздела: Список использованных источников`.

### BUG-003 — отсутствуют базовые metadata, robots.txt и sitemap.xml

**Status:** **FIXED + VERIFIED**

В SPA shell добавлены description, `noindex, nofollow`, canonical для login, Open Graph title/description/type. В `frontend/public` добавлены реальные `robots.txt` и `sitemap.xml`.

Приложение является аутентифицированным workspace, поэтому robots запрещает индексацию, а sitemap намеренно не перечисляет private routes.

**HTTP verification:**

| URL | Status | Content-Type | Result |
| --- | ---: | --- | --- |
| `/login` | 200 | `text/html` | Metadata present |
| `/robots.txt` | 200 | `text/plain` | Static text file, not SPA HTML |
| `/sitemap.xml` | 200 | `text/xml` | Valid XML shell, no private routes |

## Automated regression

| Command | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm test` | PASS — 9 files, 34 tests |
| `npm run build` | PASS |
| `npm run test:e2e` | PASS — 2 Playwright tests |

The first implementation run exposed two **test/infrastructure issues**, not application defects: a Vitest file-path assumption and a stale Vite process. Both were corrected before the final passing run.

## Remaining readiness considerations

- Full backend pytest still needs a host environment with its `redis` dependency, or a retained containerized test result.
- Lighthouse and a production Nginx deployment smoke test were outside this regression run.
- The document-editor chunks remain relatively large and should be monitored with real-user performance data.
