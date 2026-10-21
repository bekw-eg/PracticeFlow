# Первая организация и первый Super Admin

Команда `python -m app.cli.bootstrap` предназначена для первого запуска на
пустой базе с применёнными миграциями. Она доступна только оператору с доступом
к приватному backend-контейнеру и его deployment credentials. Публичного HTTP
endpoint для bootstrap нет. Development seed запускать не требуется.

## Подготовка

1. Подготовьте production env вне Git по [README](../README.md#production-deployment)
   и [release runbook](RELEASE_RUNBOOK.md). Используйте `ENV=production`,
   `SEED_ON_START=false` и все обязательные production secrets, MFA keys,
   private S3, Redis, cookie, proxy, audit и resource settings. CLI загружает
   обычный `Settings`, требует `ENV=production` и не отключает ни одну
   production-проверку.
2. Проверьте целевой deployment project и базу. Не экспериментируйте на
   существующем tenant. Запускайте bootstrap до открытия пользовательского
   трафика; PostgreSQL должен быть доступен, а миграции — применены.
3. Выберите реальный email, имя администратора, название и slug организации.
   Все значения ниже вымышленные; замените их своими. Имена имеют длину
   2–255 символов, slug — 2–100 символов в формате `example-academy`.
   Email проходит ту же нормализацию `EmailStr`, что и обычный вход.
4. Подготовьте уникальный пароль в менеджере секретов. Действует обычная
   политика приложения: 8–72 UTF-8 байта, без обрезки bcrypt. Не передавайте
   пароль в аргументах, переменных окружения, `.env`, shell history, Git,
   CI output или записи терминала.

## Запуск на deployment host

В примерах `practiceflow-example` — вымышленное имя Compose project.
Используйте имя уже подготовленного deployment, чтобы обратиться к его сети
и базе. Backend image должен содержать эту CLI-команду. Сначала поднимите
PostgreSQL в этом deployment и примените миграции обычным способом, например:

```bash
docker compose --project-name practiceflow-example --env-file .env.production \
  -f docker-compose.prod.yml run --rm --no-deps --entrypoint alembic \
  backend upgrade head
```

Затем запустите интерактивный bootstrap:

```bash
docker compose --project-name practiceflow-example --env-file .env.production \
  -f docker-compose.prod.yml run --rm --no-deps --entrypoint python \
  backend -m app.cli.bootstrap \
  --organization-name "Example Academy" \
  --organization-slug example-academy \
  --admin-email first-admin@example.org \
  --admin-full-name "Example Operator"
```

CLI дважды запросит пароль со скрытым вводом. Если безопасный terminal input
недоступен, команда завершится с ошибкой, без перехода к отображаемому вводу.
`--entrypoint python` запускает непосредственно CLI, без server entrypoint,
автомиграций и seed. Нельзя заменять `ENV=production` на development для
обхода ошибки конфигурации.

Для автоматизации используйте `--password-stdin`: одобренный менеджер секретов
должен передать один пароль напрямую через приватный pipe и закрыть stdin.
В Compose добавьте `-T`, чтобы отключить TTY:

```bash
# stdin подключается к выводу вашего одобренного secret reader.
# В самой команде и её аргументах пароля нет.
docker compose --project-name practiceflow-example --env-file .env.production \
  -f docker-compose.prod.yml run --rm --no-deps -T --entrypoint python \
  backend -m app.cli.bootstrap \
  --organization-name "Example Academy" \
  --organization-slug example-academy \
  --admin-email first-admin@example.org \
  --admin-full-name "Example Operator" --password-stdin
```

Не используйте `echo` с паролем, shell command substitution или временный файл
с паролем. Допустим один завершающий LF/CRLF; пробелы пароля сохраняются.
Пароль нельзя передать через `--password`. Для установки без контейнера
выполните ту же команду `python -m app.cli.bootstrap` из каталога `backend`
в подготовленном production environment.

## Что создаётся и как повторять

В одной транзакции создаются недостающие записи каталога ролей
`SUPER_ADMIN`, `DIRECTOR`, `TEACHER`, `STUDENT`, одна организация, один активный
пользователь с bcrypt hash и один активный membership `SUPER_ADMIN`.
В той же транзакции сохраняются audit events `ORGANIZATION_CREATED` и
`MEMBERSHIP_CREATED` с признаком `bootstrap`, без пароля и персональных полей
в metadata. Существующий каталог ролей используется без изменения его записей.
Сбой любого шага откатывает всю операцию.

Команда блокирует конкурентные записи в identity-таблицы до завершения
транзакции, включая время скрытого ввода. При занятой базе ожидание получения
блокировки ограничено пятью секундами. Дождитесь окончания другого writer и
повторите команду; не отключайте блокировки и не удаляйте данные.

Повтор с теми же email, slug, именем пользователя и названием организации
возвращает `Already initialized` и код `0`, если пользователь и membership
активны и membership уже имеет `SUPER_ADMIN`. Пароль повторно не запрашивается,
не проверяется и не меняется; MFA, sessions, роли и audit остаются прежними.
Это проверка состояния базы для оператора, а не проверка пароля.

Любые другие существующие пользователи/организации/membership без точного
совпадения приводят к `Bootstrap refused` и коду `1`. В том числе запрещены
добавление второго tenant, присоединение существующего пользователя,
повышение его роли и реактивация. Отличающийся регистр существующего email
также не позволяет создать дубль или присвоить права. После переименования,
смены роли или деактивации используйте обычное администрирование. У CLI нет
флагов `force`, сброса пароля или обхода MFA; такое действие выполняется
явно через соответствующий authenticated administration/recovery workflow.

Ошибки ввода/пароля, неподготовленная схема, недоступность базы и конфликт
сопровождаются безопасным сообщением без SQL, конфигурационных значений или
traceback. Некорректные CLI options возвращают код `2`; отмена ввода — `1`.
Если соединение оборвалось при commit и результат неизвестен, повторите
исходную команду: она либо завершит создание, либо подтвердит существующее
состояние без изменения пароля. Не очищайте базу для повторного запуска.

## Первый вход и MFA

1. Откройте production UI по HTTPS. Войдите с выбранными slug, email и паролем.
2. Ожидаемый password-stage ответ — `202 MFA_ENROLLMENT_REQUIRED`, без access
   и refresh tokens. До подтверждения TOTP доступ к защищённому API закрыт.
3. Добавьте показанный QR/manual key в authenticator и подтвердите TOTP.
   Только после подтверждения сервер создаёт MFA-bound session и Secure,
   HttpOnly refresh cookie.
4. Сохраните десять одноразовых recovery codes в одобренном защищённом месте.
   При следующем входе потребуется `MFA_REQUIRED`. Не сохраняйте QR/manual
   key, recovery codes или session tokens в логах, screenshots или Git.
5. Проверьте Super Admin role и доступ к нужной организации. После bootstrap
   повторная команда сохраняет уже настроенный MFA factor и действующие sessions.

CLI не создаёт MFA factor заранее и не выдаёт session, recovery code или
break-glass challenge. Потеря пароля и MFA решается существующими
[процедурами аутентификации и восстановления](../README.md#mfa-для-director-и-super-admin).
Доступ к shell и credentials deployment остаётся отдельной доверенной
операторской границей; эта команда не заменяет защиту deployment host.

## Проверка и rollback

Для проверки используйте только отдельную disposable PostgreSQL базу с именем
`*_test`. Тесты `app/tests/test_bootstrap.py` покрывают production CLI со stdin,
создание на пустой базе, повтор, конфликты, rollback, конкурентный запуск,
password/config guards и первый HTTPS login с TOTP enrollment через обычные
API routes. В тестах production configuration проверяется без обращения к
реальным Redis/S3; эти зависимости и внешний HTTPS deployment дополнительно
проверяются обычным release smoke test.

Изменений схемы нет, новые миграции не нужны. Rollback приложения не удаляет
созданные identities или MFA. После успешного создания управляйте доступом
через обычное администрирование; не удаляйте tenant и не запускайте seed.
Очистка допустима только для выделенного disposable test project.
