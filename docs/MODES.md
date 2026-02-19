# Режимы и возможности инструмента

Этот документ фиксирует актуальные режимы запуска и их назначение.

## 1) Обычное резюме по одной задаче

- Что делает: генерирует общее резюме по одной Jira-задаче.
- Команда:

```bash
python main.py MSP-1234
```

- Дополнительно:

```bash
python main.py MSP-1234 --json --log-level DEBUG
```

- Шаблон: `PROMPT_TEMPLATE_PATH` (по умолчанию `prompt_templates/release_summary.txt`).

## 2) Одна строка релизной таблицы по задаче

- Что делает: генерирует только краткое описание для одной задачи (формат строки релизной таблицы), выводит в консоль.
- Команда:

```bash
python main.py --issue-short MSP-1234
```

- Логика шаблонов:
- если задан `ISSUE_SHORT_TEMPLATE_PATH` -> он используется для всех типов задач;
- иначе для `Баг` используется `ISSUE_SHORT_BUG_TEMPLATE_PATH`, для остальных типов (`Фича`, `История` и т.д.) — `ISSUE_SHORT_FEATURE_TEMPLATE_PATH`.

## 3) Релизная таблица: просмотр без записи

- Что делает: собирает задачи релиза (Relates от `RELEASE_PARENT_KEY`), генерирует краткие описания и печатает готовую Jira-таблицу в консоль.
- Требуется: `--release-parent` или `RELEASE_PARENT_KEY`.
- Команда:

```bash
python main.py --release-parent MSP-7000 --mode view
```

## 4) Релизная таблица: заполнение в Jira

- Что делает: как `view`, но записывает таблицу в описание `TARGET_ISSUE_KEY` (или `--release-target`).
- Требуется: `--release-parent`/`RELEASE_PARENT_KEY` и `--release-target`/`TARGET_ISSUE_KEY`.
- Команда:

```bash
python main.py --release-parent MSP-7000 --release-target MSP-8000 --mode fill
```

- Особенность: колонки `Шаблоны` и `Мануал` сохраняются из текущей таблицы.

## 5) Релизная таблица: fill-preview в файл

- Что делает: прогоняет генерацию по всем задачам релиза без записи в Jira, результат сохраняет в файл.
- Требуется: `--release-parent` или `RELEASE_PARENT_KEY`.
- Команда:

```bash
python main.py --release-parent MSP-7000 --mode fill-preview
```

- По умолчанию файл: `docs/release_fill_preview.md`.
- Можно задать путь:

```bash
python main.py --mode fill-preview --preview-path docs/my_preview.md
```

## 6) Compare: эталон vs сгенерированное

- Что делает:
- берет таблицу из `TARGET_ISSUE_KEY`;
- генерирует краткие описания только для задач, которые уже есть в этой таблице;
- дописывает сгенерированный блок в колонку `Краткое описание`;
- вызывает LLM-судью и публикует отчет комментарием в Jira-задачу.
- Требуется: `--release-target`/`TARGET_ISSUE_KEY`. Также нужен `--release-parent`/`RELEASE_PARENT_KEY` для входа в release-ветку.

- Команда:

```bash
python main.py --release-parent MSP-7000 --release-target MSP-8000 --mode compare --compare-mode replace --log-level DEBUG
```

- Варианты `--compare-mode`:
- `replace` — заменяет предыдущий блок `_Сгенерировано:_`;
- `append` — добавляет новый блок `_Сгенерировано #N:_`.

- Если нужно обновить только таблицу без судьи:

```bash
python main.py --mode compare --skip-judge
```

- Переменные для судьи:
- `JUDGE_PROMPT_PATH` (по умолчанию `prompt_templates/judge_release_table.txt`);
- `JUDGE_SYSTEM_PROMPT` (опционально);
- `JUDGE_MAX_TOKENS` (опционально).

## 7) Refine: улучшение уже заполненной таблицы

- Что делает: берет существующую таблицу в `TARGET_ISSUE_KEY` и улучшает тексты в колонке `Краткое описание` через отдельный refine-промпт.
- Требуется: `--release-target`/`TARGET_ISSUE_KEY`.

- Превью без записи в Jira:

```bash
python main.py --mode refine-preview --release-target MSP-8000
```

- Файл превью: `docs/release_refine_preview.md`.

- Применение в Jira:

```bash
python main.py --mode refine-apply --release-target MSP-8000
```

- Шаблон refine: `REFINE_PROMPT_PATH` (по умолчанию `prompt_templates/refine_release_summary.txt`).

## 8) Вспомогательные скрипты

- Проверка санитайзера на задаче:

```bash
python scripts/check_sanitizer.py MSP-8440
```

- Просмотр итогового refine-промпта (debug):

```bash
python scripts/show_refine_prompt.py
```

## Базовые переменные .env

- Обязательные для работы: `JIRA_BASE_URL`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE`, `LLM_ENDPOINT`.
- Для `basic`-авторизации также обязателен `JIRA_EMAIL`.
- Для релизных режимов нужны: `RELEASE_PARENT_KEY` и/или `TARGET_ISSUE_KEY` (если не передаете их флагами).
