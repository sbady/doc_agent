# Task Contract

Subordinate to `docs/AGENT_WORKFLOWS.md` and the repo `AGENTS.md`.

## Minimum useful input

- `task_key` (Jira key, e.g. `MSP-9479`)
- `repo`: usually `doc_diplo`
- `base_branch`: usually `main`
- `intent`: `edit` (apply + publish) or `draft` (prepare + show only)

For `intent = edit`, push + MR into `DEV` + mirror MR into `main` + conflict checks are the **default** — they don't need to be requested.

## Good request template

```text
Задача: MSP-XXXX
Репозиторий: doc_diplo
Базовая ветка: main
Намерение: внести правки и опубликовать (по умолчанию)
Ограничения:
- не включать Tasks в git
- без прямых правок в main/DEV
```

If the user only wants a draft, say so explicitly:

```text
Намерение: только черновик, не пушить
```

## Safe defaults if something is missing

- repo = `doc_diplo`
- base branch = `main`
- branch name = Jira key
- commit message = Jira key
- intent = `edit` → publish to `DEV`, mirror to `main`, return both MR links + conflict checks

Ask only when a missing value materially changes behavior (e.g. unclear which article, unclear contour, contradictory context).
