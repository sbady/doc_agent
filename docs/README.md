# Автоматизация Release Notes из Jira

Инструмент помогает готовить релизные заметки для пользовательской документации продукта на основе задач Jira: собирает задачи релиза, генерирует для них краткие формулировки через LLM и формирует/обновляет таблицу релиза в описании целевой Jira‑задачи.

Подробная логика и правила: `docs/FEATURE_SPEC.md`.

## Как это работает (кратко)

1. Забирает из Jira `summary/description/comments/issuetype`.
2. Санитизирует текст (маскировка токенов/хостов/логов и т.п.) перед отправкой в LLM.
3. Для релиз‑режима: из родительской релизной задачи берёт связанные задачи типа **Relates**, определяет стенд (MS/WCE/Оба/Оба?), тип (Баг/Фича), генерирует краткое описание и строит Jira wiki‑таблицу.
4. В режиме `fill` обновляет только блок таблицы в описании целевой задачи (идемпотентно), сохраняя колонки «Шаблоны»/«Мануал».
5. В режимах `refine-preview/refine-apply` шлифует уже существующие тексты в колонке «Краткое описание».

## Подготовка окружения

1. **Python**: требуется Python 3.9+.
2. **Виртуальное окружение (опционально)**:
   ```bash
   python -m venv .venv
   .venv\\Scripts\\Activate.ps1
   ```
3. **Установка зависимостей**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Настройка `.env`**: возьмите за основу `env_example` и заполните реальные значения.

## Основные переменные окружения (.env)

- Jira: `JIRA_BASE_URL`, `JIRA_AUTH_TYPE` (`basic`/`pat`), `JIRA_EMAIL` (для `basic`), `JIRA_API_TOKEN`, `JIRA_API_VERSION`
- LLM: `LLM_ENDPOINT`, `LLM_MODEL` (для `/v1/chat/completions`), `LLM_API_KEY` (опционально), `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`
- Шаблоны: `PROMPT_TEMPLATE_PATH`, `ISSUE_SHORT_FEATURE_TEMPLATE_PATH`, `ISSUE_SHORT_BUG_TEMPLATE_PATH`, `ISSUE_SHORT_TEMPLATE_PATH` (опционально, общий оверрайд), `ISSUE_SHORT_MAX_TOKENS`, `ISSUE_SHORT_SYSTEM_PROMPT`
- Релиз‑режим: `RELEASE_PARENT_KEY`, `TARGET_ISSUE_KEY`
- Refine: `REFINE_PROMPT_PATH`, `REFINE_SYSTEM_PROMPT`, `REFINE_MAX_TOKENS`
- Санитайзер: `SANITIZER_MODE` (`strict`/`soft`)

## Запуск

### Одиночное резюме по задаче

- Обычный вывод: `python main.py MSP-7906`
- С исходными данными (для отладки): `python main.py MSP-7906 --json --log-level DEBUG`

### Релиз‑таблица (таблица задач релиза)

- Просмотр таблицы (без изменений в Jira): `python main.py --release-parent MSP-XXXX --mode view`
- Заполнение/обновление таблицы в целевой задаче: `python main.py --release-parent MSP-XXXX --release-target MSP-YYYY --mode fill`

### Refine (шлифовка уже заполненной таблицы)

- Превью правок в `docs/release_refine_preview.md`: `python main.py --mode refine-preview --release-target MSP-YYYY`
- Применение правок в Jira: `python main.py --mode refine-apply --release-target MSP-YYYY`

### Проверка санитайзера

- Сравнение raw vs sanitized: `python scripts/check_sanitizer.py MSP-8440`

## Ограничения

- `fill/refine-*` работают только если описание задачи в Jira доступно как wiki‑строка (Jira Server/DC). Для Jira Cloud (ADF) требуется отдельная реализация обновления описания.

## Web UI (MVP)

Интерфейс-обертка над текущими CLI-командами:

```bash
streamlit run ui/app.py
```

Что есть в UI сейчас:
- обзор процесса актуализации документации;
- генерация одной релизной строки;
- preview релизной таблицы без записи в Jira;
- заполнение релизной таблицы в Jira;
- compare эталон vs сгенерированное;
- проверка санитайзера;
- сканирование документации на стоп-слова;
- история запусков.

Подробная спецификация и статус реализации: `docs/INTERFACE_SPEC.md`.

python main.py --issue-short MSP-7401

python main.py --mode fill --log-level DEBUG

python main.py --mode fill-preview --log-level DEBUG

python main.py --mode refine-preview --log-level DEBUG

python main.py --mode refine-apply --log-level DEBUG

python scripts/check_sanitizer.py MSP-8440 
