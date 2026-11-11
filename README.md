# Money — бесплатный Telegram-контент-завод на GitHub Actions

Готовый MVP для канала «Деньги без паники»: утверждённый JSON → проверка → фирменная карточка 1080×1350 → Telegram. Тексты можно создавать вручную по `prompts/MASTER_PROMPT.md`; платный LLM и image API не требуются.

## Важно для репозитория `andrey9653246431-spec/money`

ZIP-файлы в корне репозитория не запускаются. Нужно удалить их из GitHub, распаковать `money-ready.zip` на компьютере и загрузить **содержимое архива** в корень репозитория, а не сам ZIP.

Правильный результат в корне `money`:

```text
.github/workflows/publish.yml
assets/
brand/
content/
design_factory/
docs/
examples/
prompts/
schemas/
scripts/
state/
pyproject.toml
README.md
```

## 1. Загрузите файлы через GitHub Web

### Автоматическая распаковка прямо в GitHub

Если не хотите распаковывать архив на компьютере:

1. Один раз добавьте `.github/workflows/unpack-money-ready.yml` из пакета через **Add file → Create new file**.
2. Загрузите `money-ready.zip` в корень репозитория через **Add file → Upload files**.
3. Откройте **Actions → Unpack money-ready.zip → Run workflow**.
4. Workflow проверит пути в архиве, распакует содержимое, удалит ZIP и сделает commit в `main`.

Если push будет отклонён, проверьте, что ветка `main` разрешает запись GitHub Actions и не защищена от прямых commit. После распаковки продолжите с раздела 2.

### Ручная альтернатива

1. Скачайте и распакуйте `money-ready.zip`.
2. В репозитории откройте **Add file → Upload files**.
3. Перетащите файлы и папки **из распакованной папки**, включая скрытую `.github`.
4. Проверьте, что `.github/workflows/publish.yml` находится именно в корне репозитория, а не в дополнительной вложенной папке `money-ready/`.
5. Нажмите **Commit changes** в ветку `main`.
6. Старые `dengi-bez-paniki-design-factory.zip`, `dengi_bez_paniki_content_factory.zip` и `shopping_bot.zip` можно удалить: они не нужны Actions.

## 2. Проверьте Secrets

Откройте **Settings → Secrets and variables → Actions → Secrets** и убедитесь, что существуют имена:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Используйте токен BotFather и ID/username тестового канала. Не вставляйте значения в файлы репозитория.

## 3. Оставьте расписание выключенным

На вкладке **Settings → Secrets and variables → Actions → Variables** создайте:

```text
Name: PUBLISHING_ENABLED
Value: false
```

Пока значение `false`, cron не публикует. Ручной dry-run всё равно доступен.

## 4. Добавьте утверждённый тестовый день

В пакете есть `content/examples/approved-example.json`. Для теста скопируйте его содержимое в новый файл:

```text
content/approved/2026-11-12.json
```

Через GitHub Web: **Add file → Create new file**, укажите путь выше, вставьте JSON и нажмите **Commit changes**.

Это демонстрационные посты без актуальных цен. Сначала публикуйте их только в тестовом канале. Для другого дня замените `date`, `content_id`, тексты, `reviewer`, `approved_at` и проверьте `status=approved`.

## 5. Запустите dry-run

1. Откройте **Actions**. Если GitHub предложит, включите workflows.
2. Выберите **Publish approved Telegram content**.
3. Нажмите **Run workflow** и укажите:

```text
slot: morning
content_date: 2026-11-12
dry_run: true
```

4. Дождитесь зелёного результата и скачайте artifact с PNG.
5. Проверьте логи `Validate approved JSON`, `Render cards` и `Publish one slot or dry-run`.

Dry-run не требует валидного Telegram-токена, не отправляет сообщения и не меняет state.

## 6. Отправьте тестовый пост

Повторите **Run workflow** с теми же датой и слотом, но:

```text
dry_run: false
```

Workflow вызовет `sendPhoto`, сохранит `message_id`, запишет state и сделает commit `[skip ci]`. Повторный запуск того же поста должен показать `SKIP`, а не создать дубль.

Затем отдельно проверьте `day` и `evening`. Дневной длинный пост отправляется как фото и последующий текст. Caption коротких постов ограничен безопасными 1000 знаками; текстовые сообщения разбиваются до 3900.

## 7. Включите основной канал и расписание

1. После тестов замените значение `TELEGRAM_CHAT_ID` на ID основного канала.
2. Создайте реальные approved JSON для нужных дат.
3. Ещё раз запустите один пост вручную.
4. Измените Variable:

```text
PUBLISHING_ENABLED=true
```

Cron запускается примерно в 09:03, 13:03 и 20:03 по Москве. GitHub Actions может задерживать scheduled jobs. В день публикации соответствующий файл должен называться `content/approved/YYYY-MM-DD.json`, а workflow должен находиться на `main`.

## Локальная проверка перед загрузкой

Нужен Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python scripts/validate_content.py \
  --file content/examples/approved-example.json \
  --slot morning --require-approved

dbp-design build \
  --input content/examples/approved-example.json \
  --out dist/example

python scripts/publish_telegram.py \
  --content content/examples/approved-example.json \
  --slot morning --image-dir dist/example \
  --state-dir state/telegram --archive-dir content/published \
  --dry-run true

ruff check .
ruff format --check .
pytest
```

## Бесплатный режим

- Используется только стандартный `ubuntu-latest`.
- Текстовый и image API не вызываются.
- Artifact хранится 7 дней.
- Для публичного репозитория стандартные GitHub-hosted runners бесплатны; для приватного используйте включённую квоту GitHub Free и следите за ней.
- Публичный репозиторий делает видимыми все approved JSON и будущие посты. Не помещайте туда приватные источники и персональные данные.

## Если что-то не работает

| Ошибка | Причина и действие |
|---|---|
| `No such file content/approved/...` | Проверьте дату, имя файла и отсутствие лишней вложенной папки |
| `dbp-design: not found` | Не загружены `pyproject.toml`, `design_factory/`, `assets/`, `brand/` |
| `status != approved` | Пост не утверждён или забыты reviewer/approved_at |
| `401` | Проверьте токен бота |
| `403` | Добавьте бота администратором канала с правом публикации |
| `400` | Проверьте chat_id, PNG и длину текста |
| `429` | Скрипт учитывает retry_after; не запускайте параллельные копии |
| Cron не публикует | `PUBLISHING_ENABLED=true`, файл на main, есть approved JSON текущей московской даты |
| Повторная отправка | Не удаляйте `state/telegram`; проверьте существующий message_id в канале |

Подробное ТЗ и редакционные правила находятся в `docs/` и `prompts/`.
