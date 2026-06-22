---
name: git-workflow
description: Manage Git for documentation tasks in `doc_diplo`. Use when Codex/Claude needs to create a task branch from `main`, publish changes to `DEV` and mirror them to `main`, create merge requests into both branches by default, check conflicts against both targets, or resolve documentation merge conflicts safely. Subordinate to `docs/AGENT_WORKFLOWS.md` and the repo `AGENTS.md` — follow them when they say more.
---

# Git Workflow

Handle Git for documentation tasks predictably and safely. This skill is **subordinate** to `docs/AGENT_WORKFLOWS.md` (canonical process) and the repo `AGENTS.md` (branch model + Definition of Done). If anything here is narrower than those, follow them.

## Quick Start

1. Read [references/rules.md](references/rules.md)
2. Read [references/task-contract.md](references/task-contract.md)
3. Read [references/safe-sequence.md](references/safe-sequence.md)
4. Confirm the target repository is `doc_diplo` before running commands

## Branch model

`doc_diplo` has two long-lived working branches: **`main`** (prod) and **`DEV`** (dev stand, for review). Both must exist and be pushed. If the working `main` branch is missing or unpushed, that is a state error — create/push it before opening an MR.

- Cut the task branch **from `main`**, named exactly as the Jira key (e.g. `MSP-9479`). Branching from `main` avoids dragging unapproved `DEV`-only content.
- Changes flow to **`DEV`** first (review on the dev stand), then mirror to **`main`** (prod). `DEV` and `main` must not diverge on approved content.
- If `DEV` and `main` have materially diverged, do **not** merge `DEV` into the branch meant for `main`. Prepare a separate branch off `DEV` for the DEV-MR and a separate branch off `main` for the main-MR.
- Never edit `main`/`DEV` directly — only via MR.

## Default Definition of Done (edit-intent tasks)

When the task means "apply edits" (not "draft only" / "just show me"), do the full bundle **by default, without being asked**:

1. Create/verify the task branch from `main`.
2. After `doc-writer` applies edits, inspect `git status` and the diff.
3. Stage **only** article changes / `toc.yaml` / related assets. Exclude `Tasks` and anything unrelated.
4. **Publish to `DEV`:** commit, push, **create the merge request into `DEV` and return its link.**
5. **Mirror to `main`:** carry the same changes into the working `main` branch, push, create the MR into `main`, return its link.
6. **Check conflicts against both targets separately** (`DEV` and `main`).
7. Hand the result to `doc-writer`/orchestrator so the **Jira comment** can be prepared (format in `AGENT_WORKFLOWS.md`).

Do **not** make the user re-ask for the MR link or the Jira comment — they are part of done.

### When NOT to push/MR

Stop at "edits prepared, diff shown" only when:
- the user said "draft only" / "just show me" / "don't push";
- the task is filling/reviewing the Jira release table (different deliverable — see canon);
- context is insufficient for a safe edit — then stop and ask.

## Workflow

### 1. Preflight
- check current branch; check the tree is clean
- surface unrelated local changes; never overwrite or revert them
- verify both `main` and `DEV` exist and are pushed

### 2. Create or verify the task branch
- fetch remote state if needed
- branch from `main`; name = Jira key
- if the branch exists, verify its name matches the task and it is the intended branch

### 3. Protect scope
- include only `doc_diplo` article sources, related images/assets, and `toc.yaml` if navigation changed
- if `Tasks` files appear in status, explicitly do not stage them

### 4. Review
- show changed files and a short diff summary
- confirm scope matches the task

### 5. Publish (default for edit-intent tasks)
- commit (default message = Jira key)
- push the task branch
- create the MR into `DEV`; mirror to `main` and create the MR into `main`
- return both MR links

## Conflict Handling

- identify exact files; state whether textual or binary
- binary (screenshots): resolve explicitly, report which side was chosen, lose nothing
- if `DEV`/`main` diverged, follow the separate-branches rule above
- semantic article/`toc.yaml` resolution → involve `doc-writer`
- no risky history rewrites

## Output

Return a short operational summary:
- current branch (matches Jira key?)
- whether branches were created/pushed
- changed files; whether unrelated files are present
- whether commits were created and pushed
- **MR links for `DEV` and `main`**
- conflict-check result per target

## Resources

- [references/rules.md](references/rules.md)
- [references/task-contract.md](references/task-contract.md)
- [references/safe-sequence.md](references/safe-sequence.md)
