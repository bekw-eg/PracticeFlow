# Очередь приоритета в группе проверки

Очередь приоритета помогает преподавателю сразу увидеть, с каких работ в группе проверки стоит начать, не просматривая каждый документ вручную.

## Уровни приоритета и логика оценки

Чистые функции оценки и сортировки без обращения к БД и часам вынесены в [review_priority.py](../backend/app/services/review_priority.py).

Для каждой работы в группе выбирается оцениваемый запуск `DocumentCheckJob`:
- если преподаватель уже завершил проверку (`TeacherDocumentReview.completed_at IS NOT NULL`), используется закреплённый `completed_job_id`;
- иначе используется последний `COMPLETED`-запуск (`latest_completed_job`), а при его отсутствии — последний запуск (`job`).

Уровни (от наиболее срочных к наименее срочным):

1. **`FAILED`** — оцениваемый запуск завершился с ошибкой `FAILED` (требует внимания преподавателя).
2. **`RED`** — выполняется хотя бы одно условие:
   - локальная схожесть `similarity_percent >= RED_SIMILARITY_PERCENT` (только при `LocalPlagiarismRun.status == COMPLETED`);
   - `findings_truncated == True` (список замечаний упёрся в лимит анализатора);
   - при известном `paragraph_count > 0` (`density_unknown == False`):
     - `errors_per_100_paragraphs >= RED_ERRORS_PER_100_PARAGRAPHS`, или
     - `issues_per_100_paragraphs >= RED_ISSUES_PER_100_PARAGRAPHS`, где `issues = error_count + warning_count`;
   - для исторических запусков без `paragraph_count` (`density_unknown == True`):
     - `error_count >= RED_ERROR_COUNT_FALLBACK`, или
     - `(error_count + warning_count) >= RED_ISSUES_COUNT_FALLBACK`.
3. **`YELLOW`** — не `RED`, но есть хотя бы одно нарушение с severity `ERROR` или `WARNING`, либо `similarity_percent >= YELLOW_SIMILARITY_PERCENT`. Замечания с severity `INFO` уровень `YELLOW` не вызывают.
4. **`WAITING`** — завершённого запуска ещё нет, последний запуск в статусе `QUEUED` или `PROCESSING`.
5. **`GREEN`** — завершённый запуск с нулём `ERROR`/`WARNING`, без усечения списка замечаний и с локальной схожестью `< YELLOW_SIMILARITY_PERCENT` (или без завершённой проверки схожести).

## Предварительные (provisional) пороги

Значения констант в [review_priority.py](../backend/app/services/review_priority.py) являются **предварительными (provisional)** — они проверены только на формулах и одной курсовой работе (`n = 1`, `367` абзацев `<w:p>`, `2 ERROR` и `225 WARNING` при стандартных правилах):

| Константа | Значение | Назначение |
| --- | ---: | --- |
| `RED_SIMILARITY_PERCENT` | `30.0` | Порог локальной схожести (%) для `RED` |
| `YELLOW_SIMILARITY_PERCENT` | `10.0` | Порог локальной схожести (%) для `YELLOW` |
| `RED_ERRORS_PER_100_PARAGRAPHS` | `15.0` | Порог `ERROR` на 100 проверенных абзацев для `RED` |
| `RED_ISSUES_PER_100_PARAGRAPHS` | `120.0` | Порог `ERROR + WARNING` на 100 проверенных абзацев для `RED` |
| `RED_ERROR_COUNT_FALLBACK` | `15` | Запасной абсолютный порог `ERROR` без `paragraph_count` |
| `RED_ISSUES_COUNT_FALLBACK` | `120` | Запасной абсолютный порог `ERROR + WARNING` без `paragraph_count` |

## Единица «абзац» (`paragraph_count`)

Начиная с `ANALYZER_VERSION = "phase-2.6.0"` ([document_analyzer.py](../backend/app/services/document_analyzer.py)), анализатор аддитивно записывает `result_summary.paragraph_count` — число непустых абзацев `<w:p>` внутри проверяемой области (после исключения титульного листа и исключённых страниц `page_exclusions`). `LocalPlagiarismIndex.paragraph_count` для плотности не используется, так как считает другую выборку абзацев. Для старых запусков без `paragraph_count` API возвращает `density_unknown: true` и применяет абсолютные запасные пороги.

## Порядок сортировки

1. Сначала работы, ещё не проверенные преподавателем (`is_reviewed_by_teacher = false`), затем проверенные (`true`).
2. Уровень: `FAILED` → `RED` → `YELLOW` → `WAITING` → `GREEN`.
3. Внутри уровня: по убыванию `similarity_percent`, затем по убыванию `error_count`, затем по убыванию `error_count + warning_count`, затем более ранние `submitted_at`, затем `submission_id` для стабильности.

## API и безопасность

`GET /api/v1/document-checks/teacher/groups/{group_id}/priority-queue`

- Доступен только владельцу группы (проверка `organization_id` и `teacher_id`, чужая группа — `404`, неподходящая роль — `403`), заголовок `Cache-Control: private, no-store`.
- Подсчёт `ERROR` и `WARNING` выполняется одним агрегирующим SQL-запросом по `job_id` и `severity` без загрузки `DocumentCheckFinding` и без N+1.
- Содержимое документов, отрывки и источники совпадений не возвращаются.

## Протокол калибровки порогов на 10–20 работах

Перед фиксацией порогов как постоянной политики необходимо откалибровать их на выборке из 10–20 работ:

1. **Сбор выборки**: подобрать 10–20 работ (или сгенерировать синтетический набор DOCX разного объёма — от 50 до 400 абзацев — с помощью `python-docx` / OOXML-генератора, варьируя долю абзацев с нарушением шрифта/полей/интервалов: чистые, 5–10% нарушений, 20–40% нарушений, >50% нарушений, а также с вставками совпадающих фрагментов 0%, 12%, 35%).
2. **Прогон анализатора**: загрузить работы в тестовую группу с типовым опубликованным профилем (`PAGE_FORMAT_MARGINS` = `ERROR`, `FONTS_SIZES` = `ERROR`, `PARAGRAPH_SPACING_INDENTS` = `WARNING`) и запустить анализ и локальную проверку схожести.
3. **Сбор метрик**: из ответа `/priority-queue` собрать распределение `errors_per_100_paragraphs`, `issues_per_100_paragraphs` и `similarity_percent` (квантили p25, p50, p75, p90).
4. **Экспертная сверка**: преподаватель независимо размечает 10–20 работ как «срочно / с замечаниями / чисто», после чего пороги `RED_*` и `YELLOW_*` корректируются так, чтобы минимизировать ложные срабатывания `RED` на работах с мелкими единичными отступлениями.
