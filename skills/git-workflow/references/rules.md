# Git Rules

Subordinate to `docs/AGENT_WORKFLOWS.md` and the repo `AGENTS.md`.

## Repository

- Default: `doc_diplo`

## Branches

Two long-lived working branches: `main` (prod) and `DEV` (dev stand). Both must exist and be pushed.

- Task branch base: **`main`**
- Task branch name: **the Jira key**, e.g. `MSP-9479`
- Never edit `main`/`DEV` directly — only via MR
- If `DEV` and `main` diverged materially: separate branch off `DEV` for the DEV-MR, separate branch off `main` for the main-MR

## Commit

- Default commit message: the Jira key, e.g. `MSP-9479`
- If the user gives a different convention, follow it

## Push & MR — default policy

For **edit-intent** tasks (apply changes, not draft-only), the default is:

- push the task branch
- create the MR into `DEV` and return its link
- check conflicts against `DEV`
- **do NOT create the MR into `main` by default** — it would stay open through the whole review cycle. Publishing to `main` (branch from `main` + MR into `main`) is a separate step the user initiates once the task is approved

Do **not** wait for the user to re-ask for push, the DEV MR link, or the Jira comment.

Commit/MR messages must state **which articles changed and under which Jira task(s)** (`MSP-XXXX`). Do **not** add tool/model authorship (`Co-Authored-By`, Claude, Codex) to commits or MRs.

Stop at "edits prepared" only when the user said draft-only / don't push, or context is insufficient (then ask).

## Protected scope

Git must contain only clean documentation changes for the task.

- do not stage files from `Tasks`
- do not stage local drafts, configs, or `.env`
- `toc.yaml` only if navigation changed; assets/images only if part of the task

## Forbidden by default

- `reset --hard`
- force push
- history rewrites
- direct edits in `main`/`DEV`
- silent revert of unrelated local changes
- sweeping other agents' uncommitted work into your commit
