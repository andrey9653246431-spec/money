# Пошаговый запуск контент-завода «Деньги без паники» на GitHub для Telegram

## 0. Что получится

Рабочая схема безопасного MVP:

```text
Master-промпт + источники
        ↓
3 черновика в JSON
        ↓
Проверка редактора и Pull Request
        ↓
content/approved/YYYY-MM-DD.json
        ↓
GitHub Actions → карточка 1080×1350 → Telegram Bot API
        ↓
09:00 / 13:00 / 20:00 по Москве + журнал message_id
```

GitHub хранит контент, код, секреты и запускает автоматизацию. Telegram принимает публикации через бота. Для автоматической генерации текста нужен отдельный LLM API. Для фирменных карточек внешний генератор изображений не обязателен: используется Pillow из пакета `dengi-bez-paniki-design-factory`.

**Рекомендуемый порядок:** сначала ручная генерация по master-промпту и автоматическая публикация, затем автоматические черновики через LLM API. Не начинайте с полностью автономного канала.

---

## 1. Подготовьте тестовый Telegram-канал

1. Создайте отдельный тестовый канал, например «Деньги без паники — тест».
2. Для первого запуска проще использовать публичный канал с username: `chat_id` будет `@username`.
3. Не подключайте основной канал, пока не пройдут тесты из раздела 12.

Для приватного канала используется числовой ID. Получайте его через Telegram Bot API/лог собственного бота, а не через непроверенные сторонние сервисы.

## 2. Создайте Telegram-бота

1. Откройте официальный `@BotFather`.
2. Выполните `/newbot`, задайте имя и username.
3. Сохраните токен только в менеджер секретов; не отправляйте его в репозиторий, Issues или чаты.
4. Добавьте бота в тестовый канал как администратора.
5. Дайте минимально необходимое право — **публикация сообщений**. Остальные права для MVP не нужны.
6. Если токен случайно опубликован, сразу перевыпустите его через BotFather.

Проверка доступа без публикации:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
```

Не выполняйте команду с токеном прямо в командной строке и не сохраняйте его в shell history: сначала задайте переменную окружения в безопасном локальном окружении.

## 3. Создайте GitHub-репозиторий

Рекомендуется приватный репозиторий, например `dbp-content-factory`.

1. Создайте пустой репозиторий на GitHub.
2. Распакуйте `dengi-bez-paniki-design-factory.zip` в локальную папку.
3. Добавьте в неё `MASTER_PROMPT.md`, `GITHUB_TELEGRAM_LAUNCH.md` и каталоги контента.
4. Выполните:

```bash
git init
git add .
git commit -m "Initial Telegram content factory"
git branch -M main
git remote add origin https://github.com/ВАШ_АККАУНТ/dbp-content-factory.git
git push -u origin main
```

Целевая структура:

```text
.github/workflows/
├── generate.yml             # понадобится для автоматических черновиков
└── publish.yml              # публикация утверждённого контента
assets/ brand/ design_factory/
prompts/
└── MASTER_PROMPT.md
content/
├── inbox/                   # черновики, нельзя публиковать
├── approved/                # утверждено редактором
└── published/               # архив опубликованного
scripts/
├── generate.py              # интеграция с выбранным LLM API
├── validate_content.py      # проверка JSON и quality_gate
└── publish_telegram.py      # Telegram Bot API и журнал состояния
state/
└── telegram/                # content_id → message_id / этап отправки
tests/
```

В уже подготовленных пакетах есть master-промпт, ТЗ, рендерер карточек, примеры и CI. `generate.py` и `publish_telegram.py` являются интеграционным слоем под вашего LLM-провайдера и канал; их поведение описано ниже.

## 4. Добавьте секреты GitHub

Откройте **Settings → Secrets and variables → Actions → New repository secret**.

Обязательные для публикации:

| Secret | Содержимое |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен BotFather |
| `TELEGRAM_CHAT_ID` | `@username` тестового канала или числовой ID |

Для автоматической генерации позже:

| Secret / Variable | Содержимое |
|---|---|
| `LLM_API_KEY` | Ключ выбранного провайдера |
| `LLM_BASE_URL` | OpenAI-compatible endpoint, если применимо |
| `LLM_MODEL` | Название модели; можно вынести в Variables |
| `IMAGE_API_KEY` | Только если используете внешнюю AI-иллюстрацию |

Не записывайте секреты в YAML, JSON контента, `README`, Git commit или логи. Не выводите HTTP URL Telegram с токеном через `echo`.

## 5. Настройте защиту публикации

Универсальный вариант для приватного репозитория:

1. Откройте **Settings → Branches** и защитите `main`.
2. Запретите прямые push, если работает несколько человек.
3. Требуйте Pull Request и хотя бы один review перед merge.
4. Публикация разрешена только из `content/approved/` на ветке `main`.
5. Бот не должен сам перемещать файлы из `inbox` в `approved`.

Если ваш тариф и тип репозитория поддерживают **Environments → Required reviewers**, можно использовать Environment `telegram-production` для ручного production-запуска. Не ставьте обязательный approval на каждый scheduled job: три ежедневные публикации будут останавливаться и ждать повторного подтверждения. Для регулярных постов approval фиксируется заранее через PR в `approved/`, а секреты хранятся в repository secrets или доступном Environment без повторного reviewer на каждый слот. Доступность required reviewers и environment secrets зависит от тарифа и публичности репозитория. [Официальная документация Environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## 6. Подготовьте первый день контента

### Вариант A — рекомендуется для первого запуска

1. Скопируйте `MASTER_PROMPT.md` в выбранный чат LLM.
2. Заполните `DATE`, темы трёх слотов, `AUTHOR_OBSERVATIONS` и `SOURCE_PACK`.
3. Получите строгий JSON.
4. Сохраните как `content/inbox/YYYY-MM-DD.json`.
5. Прогоните ручной фактчекинг из конца master-промпта.
6. Добавьте каждому посту короткий объект `card` по `prompts/art-director.md` из дизайн-завода.
7. Проверьте карточки локально:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
dbp-design validate --input content/inbox/YYYY-MM-DD.json
dbp-design build --input content/inbox/YYYY-MM-DD.json --out dist/YYYY-MM-DD
```

8. Проверьте текст, источники, цены, дисклеймеры и PNG.
9. Только после проверки установите в каждом посте:

```json
{
  "status": "approved",
  "reviewer": "ваш GitHub username",
  "approved_at": "2026-11-12T08:00:00+03:00"
}
```

10. Сохраните файл как `content/approved/YYYY-MM-DD.json` через reviewed Pull Request.

`unconfirmed_facts` остаются служебным полем и не должны попадать в `telegram_text`. `manual_review_required=true` не заменяет фактический review.

### Вариант B — автоматические черновики

`generate.yml` запускается ежедневно в 06:17 по Москве и вручную через `workflow_dispatch`:

1. Скрипт читает темы и SOURCE_PACK только из разрешённых источников.
2. LLM получает master-промпт и возвращает JSON.
3. `validate_content.py` проверяет схему, запрещённые фразы, UTM, Markdown, обязательные `quality_gate` и исключение неподтверждённых фактов из текста.
4. Рендерятся карточки и сохраняются как Actions artifact.
5. Скрипт создаёт ветку и Pull Request в `content/inbox/`.
6. LLM не получает `TELEGRAM_BOT_TOKEN` и не может вызвать публикацию.

Для генерационного job достаточно `contents: read` и `pull-requests: write`; Telegram secrets ему не нужны. Не запускайте непроверенный код из fork PR с доступом к секретам и не используйте `pull_request_target` для исполнения чужих изменений.

## 7. Проверяйте JSON перед публикацией

`validate_content.py` должен останавливать pipeline, если:

- дата файла не совпадает с датой публикации;
- слот отсутствует или повторяется;
- `status != approved`;
- нет `reviewer` и `approved_at`;
- любой `quality_gate` равен false или отсутствует;
- текст содержит UTM, Markdown-заголовки или фиктивные источники;
- неподтверждённый факт дословно включён в текст;
- отсутствует `card.title`, изображение или alt-текст;
- конкретная акция не содержит URL, дату проверки, регион и условия;
- для финансовой темы `manual_review_required` не равен true.

Пример команды в CI:

```bash
python scripts/validate_content.py \
  --file content/approved/YYYY-MM-DD.json \
  --slot morning --require-approved
```

## 8. Настройте публикационный workflow

Готовый шаблон лежит в `templates/github/publish.yml`. Скопируйте его в `.github/workflows/publish.yml` и адаптируйте имена скриптов.

Ключевые элементы:

```yaml
on:
  workflow_dispatch:
    inputs:
      slot:
        type: choice
        options: [morning, day, evening]
      dry_run:
        type: boolean
        default: true
  schedule:
    - cron: '3 9 * * *'
      timezone: 'Europe/Moscow'
    - cron: '3 13 * * *'
      timezone: 'Europe/Moscow'
    - cron: '3 20 * * *'
      timezone: 'Europe/Moscow'

concurrency:
  group: telegram-production-publish
  cancel-in-progress: false
```

Cron выбран на 09:03, 13:03 и 20:03, чтобы избежать пика в начале часа. GitHub предупреждает о возможных задержках scheduled workflows; они запускаются из default branch. В актуальной документации можно задавать IANA timezone отдельно для каждого cron. [Официальная документация schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Для ручного запуска slot берётся из input. Для scheduled запуска скрипт определяет слот по `github.event.schedule`, потому что три времени не должны публиковать один и тот же пост.

## 9. Реализуйте безопасную отправку в Telegram

`publish_telegram.py` должен:

1. Получить файл, slot, image и режим `dry_run` из аргументов.
2. Проверить `state/telegram/<content_id>.json`: уже отправленный шаг не повторять.
3. Взять `telegram_text`; добавить хэштеги и реальные `source_urls` один раз.
4. Не использовать `parse_mode`, если текст не экранирован: plain text безопаснее для текущего промпта.
5. Отправить PNG через `sendPhoto`.
6. Если весь текст помещается в caption, отправить его вместе с фото. Лимит caption — **1024 знака после обработки entities**.
7. Если текст длиннее, сначала отправить фото с коротким caption или без него, затем текст через `sendMessage`; разбивать длинный текст на части до **4096 знаков** по границам абзацев.
8. Сохранить `message_id` каждого успешного ответа в state сразу после соответствующего этапа.
9. При 429 прочитать `retry_after`, подождать указанное время и повторить только этот запрос.
10. При 400 остановиться и показать безопасное описание ошибки; при 401/403 проверить токен и права, не повторять запрос бесконечно.
11. Не записывать токен в лог и не публиковать содержимое секретов в ошибках.

Telegram методы и лимиты: [официальный Bot API](https://core.telegram.org/bots/api).

**Важно про дубли:** state после каждого этапа сильно снижает риск повторной отправки. Полностью исключить дубль при падении процесса между успешным ответом Telegram и записью state невозможно без дополнительной сверки с каналом, поэтому перед повторным запуском после непонятного сбоя редактор проверяет канал вручную.

## 10. Сохраняйте журнал публикаций

Минимальная запись:

```json
{
  "content_id": "2026-11-12-day",
  "status": "published",
  "photo_message_id": 101,
  "text_message_ids": [102],
  "published_at": "2026-11-12T13:04:00+03:00",
  "sha256_image": "..."
}
```

После успеха workflow копирует контент в `content/published/`, коммитит state с сообщением `[skip ci] publish <content_id>` и загружает PNG + JSON как artifact на 7–14 дней.

Для записи в репозиторий публикационному job нужен `contents: write`. Не давайте это право генерационному LLM-job. Альтернатива для более строгой схемы — отдельная база/artifact state без commit в `main`.

## 11. Добавьте уведомление об ошибке

При падении scheduled workflow:

1. Создавайте GitHub Issue с меткой `publishing-failed`.
2. Указывайте дату, slot, content_id и ссылку на run.
3. Не включайте токен, полный HTTP URL и чувствительные данные.
4. Не создавайте новое Issue при каждом повторе: обновляйте существующее по content_id.
5. Редактор проверяет канал перед ручным retry.

## 12. Протестируйте на тестовом канале

Порядок тестов:

1. **Validation test:** JSON без approval должен быть отклонён.
2. **Render test:** все три PNG созданы, текст не обрезан.
3. **Dry-run:** Actions показывает, какой пост и файл выбраны, но не вызывает Telegram.
4. **Morning test:** короткий пост уходит одним `sendPhoto`.
5. **Day test:** длинный пост корректно уходит фото + текст.
6. **Evening/horoscope test:** сохраняется дисклеймер и визуальный макет.
7. **Idempotency test:** повторный запуск того же content_id не создаёт дубль.
8. **Rights test:** без права публикации workflow завершается понятной ошибкой.
9. **Schedule test:** один реальный scheduled запуск происходит из `main` в правильном слоте.
10. **Review test:** файл в `inbox` никогда не публикуется.

После успешных тестов замените `TELEGRAM_CHAT_ID` на ID основного канала и повторите один ручной `dry_run=false` с заранее выбранным безопасным постом.

## 13. Включите регулярную работу

Ежедневный процесс редактора:

1. До 08:30 проверить Pull Request с тремя черновиками.
2. Сверить факты, источники, условия акций, стиль и изображения.
3. Исправить или отклонить материал; не утверждать «как есть» из-за дедлайна.
4. Merge PR переносит JSON в `approved/`.
5. Проверить результаты публикаций и ошибки Actions.
6. Через 24 и 72 часа внести метрики в редакторскую таблицу.

Держите минимум шесть approved evergreen-постов в резерве. Если актуальная акция не подтверждена, публикуйте резервный материал, а не выдуманную цену.

## 14. Диагностика

| Симптом | Что проверить |
|---|---|
| `401 Unauthorized` | Токен, лишние пробелы, перевыпуск токена |
| `403 Forbidden` | Бот добавлен в канал и имеет право публикации; правильный chat_id |
| `400 Bad Request` | chat_id, слишком длинный caption, повреждённый PNG, parse mode |
| `429` | `retry_after`, частота повторов, параллельные workflow |
| Workflow не запускается по cron | Файл workflow на default branch, включены Actions, корректный cron/timezone |
| Публикуется не тот слот | Сопоставление `github.event.schedule` и slot |
| Дубли | `concurrency`, state, повторный ручной запуск, несколько репозиториев с одним ботом |
| Нет изображения | Путь manifest, `dbp-design build`, ручной visual review |
| Кракозябры | JSON и исходники в UTF-8, Manrope доступен runner |
| Случайная публикация черновика | Publisher читает только `approved/` и требует `status=approved` |

## 15. Checklist перед production

- [ ] Тестовый канал успешно принял все три формата.
- [ ] Основной канал подключён отдельным secret.
- [ ] Токен отсутствует в Git history и логах.
- [ ] Публикация возможна только из `approved/` на `main`.
- [ ] LLM-job не имеет Telegram secrets и `contents: write`.
- [ ] `quality_gate`, ручной review и visual review обязательны.
- [ ] Настроены state, concurrency, retry_after и обработка ошибок.
- [ ] Есть резервные evergreen-посты.
- [ ] Есть журнал content_id и Telegram message_id.
- [ ] Редактор понимает, как остановить workflow и перевыпустить токен.

Для аварийной остановки отключите `publish.yml` на вкладке Actions. Не удаляйте state: после восстановления он предотвратит повторную отправку уже опубликованных материалов.
