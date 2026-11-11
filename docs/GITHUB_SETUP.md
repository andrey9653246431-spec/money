# Публикация на GitHub

1. Создайте на GitHub пустой репозиторий, например `dengi-bez-paniki-design-factory`, без README и `.gitignore`.
2. Распакуйте пакет, откройте терминал в его папке и выполните:

```bash
git init
git add .
git commit -m "Initial design factory"
git branch -M main
git remote add origin https://github.com/ВАШ_АККАУНТ/dengi-bez-paniki-design-factory.git
git push -u origin main
```

3. Откройте вкладку **Actions** и разрешите workflows, если GitHub запросит подтверждение.
4. После push workflow `CI` проверит код, соберёт примеры и прикрепит PNG как artifact для Python 3.12.
5. В **Settings → Actions → General** оставьте минимально необходимые permissions: для CI достаточно `contents: read`.

Не загружайте в репозиторий `.env`, токены мессенджеров, ключи генератора изображений, персональные данные и неутверждённые рекламные материалы. Каталог `dist/` и виртуальное окружение исключены через `.gitignore`.

## Выпуск версии

```bash
git tag v1.0.0
git push origin v1.0.0
```

Перед release обновите версию в `pyproject.toml`, `design_factory/__init__.py` и `CHANGELOG.md`.
