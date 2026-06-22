---
name: doc-writer
description: Write and update Diplodoc/YFM user documentation for the event platform. Use when Codex needs to create a new article, update an existing article, adapt content for WCE/MS contours, preserve project-specific formatting, update `toc.yaml`, or prepare a documentation-ready draft from Jira context, screenshots, PDFs, or user notes.
---

# Doc Writer

Write articles for `doc_diplo` in the project's documentation style. Optimize for user clarity, factual accuracy, and minimal formatting noise.

## Quick Start

1. Read [references/context.md](references/context.md)
2. Read [references/style-guide.md](references/style-guide.md)
3. Read [references/exemplar-patterns.md](references/exemplar-patterns.md)
4. If the article targets WCE or both contours, read [references/wce-constraints.md](references/wce-constraints.md)
5. Use [references/task-input-contract.md](references/task-input-contract.md) to identify missing inputs
6. Open the target article or choose the closest exemplar article before editing

## Workflow

### 1. Build context

Collect only the inputs needed for the task:

- Jira description and comments
- provided screenshots, PDFs, DOCX exports, or local notes
- current article source, if the article already exists
- nearby articles in the same section
- `toc.yaml`, if the task introduces a new article or moves an article

If the user points to a specific task folder, read all artifacts in that folder before drafting.

### 2. Pick the right structure

Mirror the product interface. Organize the article around how the functionality appears to the user:

- section or tab in the interface
- block inside the section
- controls inside the block
- step-by-step actions in the same order the user performs them

Do not invent a theoretical structure if the interface already provides a natural one.

### 3. Draft or edit the article

When updating an article:

- preserve the existing article structure unless it is clearly broken
- change only the sections affected by the task
- preserve working YFM/Diplodoc syntax
- preserve valid screenshots, image paths, anchors, and links

When creating a new article:

- follow the metadata pattern used in exemplar articles
- use a calm structure: title, short orientation, main sections by interface blocks, notes only where they add value
- add `toc.yaml` entry if the article should appear in navigation

### 4. Handle contours correctly

If a function exists only in one contour:

- isolate it in the appropriate conditional block
- do not let that text leak into the other contour
- use separate screenshots when the interfaces differ materially

If the feature works the same way in both contours:

- keep a shared explanation
- avoid unnecessary branching

### 5. Run a quality pass

Before returning the result:

- remove unsupported assumptions
- reduce heavy bold formatting
- normalize quotes to straight quotes
- remove trailing periods from list items unless the item is a full sentence
- check that the wording stays user-facing and not internal

If asked to validate WCE wording after publication, run the stop words checker described in [references/wce-constraints.md](references/wce-constraints.md).

## Exemplar Articles

Use these as primary examples of tone, structure, and formatting:

- `doc_diplo/src/ru/documentation/org_interface/settings/main_settings/registration/entry_form.md`
- `doc_diplo/src/ru/documentation/org_interface/settings/scene_setting.md`
- `doc_diplo/src/ru/documentation/org_interface/settings/landing.md`

Use them to infer:

- metadata structure
- section depth and rhythm
- use of `note`, `cut`, conditional blocks, images, and anchors
- how much emphasis is acceptable

Do not copy irrelevant phrasing from exemplars. Reuse patterns, not boilerplate.

## Output Rules

Return exactly what the task needs:

- full ready-to-save `.md` file
- only the changed block
- article draft
- article plus `toc.yaml` update

If information is insufficient, add a short `Требует уточнения:` block at the end instead of guessing.

When summarizing your work, keep it short:

- what changed
- which files changed
- open questions, if any

## Stop Conditions

Pause and surface questions instead of guessing when:

- the target article is unclear and several locations are plausible
- the contour is unclear and affects wording materially
- the task changes product logic but the provided context is contradictory
- image or file paths cannot be inferred safely

## Resources

- [references/context.md](references/context.md)
- [references/style-guide.md](references/style-guide.md)
- [references/exemplar-patterns.md](references/exemplar-patterns.md)
- [references/wce-constraints.md](references/wce-constraints.md)
- [references/task-input-contract.md](references/task-input-contract.md)


