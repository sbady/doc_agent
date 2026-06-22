# Task Input Contract

## Minimum Useful Input

For each article task, try to collect:

- `task_key`
- `task_type`: new article or update existing article
- `target_contour`: `WCE`, `MS`, or both
- `target_article`: file path if known
- `what_changed`: short factual summary
- `sources`: Jira, comments, screenshots, PDFs, DOCX exports, local notes
- `expected_output`: full file, changed block, draft, draft plus `toc`
- `constraints`: what must not be changed

## Good Task Template

```text
Задача: MSP-XXXX
Тип: новая статья | обновление статьи
Контур: WCE | MS | оба
Путь к статье: ...
Что изменилось: ...
Источники: Jira / комментарии / PDF / скриншоты / устный контекст
Что нужно на выходе: готовый md-файл | измененный блок | черновик
Ограничения: ...
```

## If Something Is Missing

Infer safely only when the evidence is strong.

Ask for clarification when one of these materially affects the result:

- wrong target article could be chosen
- contour is unknown
- article placement in `toc` is ambiguous
- screenshot choice or path is unclear
- user needs a final file, but the current article source is unavailable

## Expected Deliverables

Depending on the task, produce one of:

- full article in Markdown/YFM
- changed block only
- patch-ready article update
- article plus `toc.yaml` change
- short change summary for review
