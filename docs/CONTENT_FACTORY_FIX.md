# Пакет исправлений контент-завода (14.11.2026)

Этот файл попал в репозиторий вместе с архивом `content-factory-fix.zip` и описывает, что именно изменилось. Подробный аудит — в отдельном документе `AUDIT-2026-11-14.md`.

## Что в пакете

| Файл | Что изменилось |
|---|---|
| `.github/workflows/price-bot.yml` | cron `0` → `7` (в начале часа у GitHub пик, запуски задерживаются); атомарная запись `state/bot/state.enc`; guard «нет файла — не коммитим»; fail-fast проверка `BOT_STATE_KEY` и токенов с `::error::`; понятная ошибка при неверном ключе; 3 попытки push с `git pull --rebase --autostash`; `PYTHONUNBUFFERED=1`; чистка `*.tmp` |
| `.github/workflows/publish.yml` | `timeout-minutes: 20`; строгая проверка даты `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`; `::warning::` и новый вход `allow_generate` для автогенерации контента; строгое сравнение `dry_run`; `git add` только существующего файла; 3 попытки push; `if-no-files-found: ignore` |
| `.github/workflows/publish-max.yml` | то же самое, шаг установки Russian Trusted CA сохранён |
| `.github/workflows/unpack-updates.yml` | тестовый гейт (`ruff` + `pytest`) **до** коммита распакованного внешнего кода |
| `.github/workflows/ci.yml` | **новый файл**: CI с матрицей Python 3.11/3.12/3.13 — `ruff check`, `ruff format --check`, `pytest`, сборка карточек и аватара, валидация JSON и dry-run публикатора |
| `price_bot/bot.py` | обработка `SIGTERM`/`SIGINT`: отменённая сессия завершается штатно и сохраняет offset |
| `.gitignore` | добавлены `state/bot/*.tmp` и `state/bot/*.enc.tmp` |
| `templates/github/*.yml` | шаблоны синхронизированы с рабочими workflow; из шаблона `price-bot.yml` убрана небезопасная схема с коммитом **открытых** JSON состояния |

Удаляется: `unpack-updates.yml` в корне репозитория (мёртвый дубль `.github/workflows/unpack-updates.yml`; GitHub его не исполняет).

## Что нужно сделать после распаковки

1. **Переменные репозитория** (Settings → Secrets and variables → Actions → Variables):
   - `PRICE_BOT_ENABLED = true` — без неё бот не запускается по расписанию (сейчас все запуски `skipped`);
   - `MAX_PUBLISHING_ENABLED = true` — если публикация в MAX нужна;
   - `PUBLISHING_ENABLED = true` — проверить, что задана (Telegram публикует, значит есть).
2. **Секреты** должны присутствовать: `BOT_STATE_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; для MAX — `MAX_BOT_TOKEN`, `MAX_CHAT_ID`.
3. `BOT_STATE_KEY` **не менять**, если в репозитории уже есть `state/bot/state.enc` — иначе старое состояние не расшифруется.
4. Если архив распаковывался workflow'ом без `WORKFLOW_PAT`, файлы workflow попали в `templates/github/` — их нужно перенести в `.github/workflows/` через веб-интерфейс GitHub (5 файлов).

## Проверка

- ручной запуск **Price comparison bot** с `session_minutes: 5`;
- в логе: `Бот запущен`, `Сессия завершена, offset сохранён`, `Состояние зашифровано: state/bot/state.enc`, коммит `[skip ci] Price bot encrypted state`;
- повторный запуск: `Состояние восстановлено` и `No state changes`;
- **Publish approved Telegram content** с `dry_run: true`: строка `DRY RUN: ...` и `Telegram API не вызывался`.
