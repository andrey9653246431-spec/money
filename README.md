# MAX — обновление для репозитория `andrey9653246431-spec/money`

Добавляет автоматическую публикацию в мессенджер MAX: тот же JSON и те же карточки, что и в Telegram, но через отдельный publisher и workflow. Полная пошаговая инструкция — `MAX_SETUP.md`.

## Файлы пакета (сохраняйте пути)

```text
scripts/publish_max.py
scripts/discover_max_chat.py
.github/workflows/publish-max.yml
.github/workflows/discover-max-chat.yml
templates/github/publish-max.yml
templates/github/discover-max-chat.yml
tests/test_max_pipeline.py
state/max/.gitkeep
docs/INTEGRATION.md
MAX_SETUP.md
```

Минимально необходимы `scripts/publish_max.py`, `scripts/discover_max_chat.py` и оба workflow. Остальное — тесты, шаблон и документация.

## Кратко

1. Создайте бота в MAX для партнёров, дождитесь модерации, скопируйте токен.
2. Добавьте бота в канал MAX как администратора.
3. Добавьте файлы из пакета в репозиторий, commit в `main`.
4. Secrets: `MAX_BOT_TOKEN`, `MAX_CHAT_ID`. Variables: `MAX_PUBLISHING_ENABLED=false`, `MAX_CHANNEL_URL` (необязательно).
5. Узнайте `chat_id`: Actions → **Discover MAX channel chat_id** → во время ожидания добавьте бота в канал → в логах `MAX_CHAT_ID=...`.
6. Dry-run: Actions → **Publish approved MAX content**, `dry_run: true`.
7. Тестовая отправка в тестовый канал (`dry_run: false`), повтор должен дать `SKIP`.
8. `MAX_PUBLISHING_ENABLED=true` — расписание 09:08/13:08/20:08 МСК.

## Проверено

- Ruff и форматирование: без ошибок;
- 27 pytest-тестов (20 старых + 7 новых для MAX);
- генерация, валидация, рендер трёх карточек и dry-run publisher для MAX;
- YAML обоих workflow разобран;
- TLS к `platform-api2.max.ru` проверен: без сертификата Минцифры — `CERTIFICATE_VERIFY_FAILED`, с Russian Trusted CA — соединение проходит (workflows устанавливают CA сами).
