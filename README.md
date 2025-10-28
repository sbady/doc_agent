# Jira Summary Generator

Инструмент генерирует краткое описание задачи из JIRA с помощью LLM (локальной или внешней).

## Подготовка окружения

1. **Python**: требуется Python 3.9+.
2. **Виртуальное окружение (опционально)**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Установка зависимостей**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Настройка `.env`**:
   - Файл `.env` уже создан.
   - Укажите реальные значения:
     - `JIRA_BASE_URL` — URL вашей Jira (например, `https://company.atlassian.net`).
     - `JIRA_AUTH_TYPE` — `basic` (email + API token) или `pat` (Bearer токен).
     - `JIRA_EMAIL` — требуется только при basic-авторизации (почта/логин).
     - `JIRA_API_TOKEN` — API токен / PAT с правами чтения.
     - `JIRA_API_VERSION` — версия REST API (`3` для Jira Cloud, `latest`/`2` для Server/DC).
     - `LLM_ENDPOINT` — URL вашего LLM (например, локальный LM Studio).
     - При необходимости заполните `LLM_API_KEY`, `LLM_MODEL` и др.

## Тест чтения задачи из Jira

1. Укажите в `.env` ключ задачи для теста: `JIRA_ISSUE_KEY=MSP-7906` (или нужный вам).
2. Запустите:
   ```bash
   python3 main.py --json
   ```
3. Убедитесь, что в выводе появился блок `source`, содержащий загруженные из Jira `title`, `description` и `comments`.

Если нужно проверить конкретный ключ без изменения `.env`, выполните:
```bash
python3 main.py MSP-7906 --json
```

## Возможные ошибки

- **401/403** — неверный email или API-токен.
- **404** — задача не найдена или нет доступа.
- **Timeout/Connection error** — проверьте URL Jira и наличие сети/VPN.

Логи пишутся в консоль. Для расширенной диагностики запустите:
```bash
python3 main.py MSP-7906 --json --log-level DEBUG
```
