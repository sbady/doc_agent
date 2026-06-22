# Safe Sequence

Subordinate to `docs/AGENT_WORKFLOWS.md` and the repo `AGENTS.md`.

## Standard sequence for an edit-intent documentation task

1. Check repo status; confirm target is `doc_diplo`
2. Confirm the Jira key
3. Verify `main` and `DEV` both exist and are pushed
4. Ensure work is not happening directly in `main`/`DEV`
5. Create or switch to `MSP-XXXX` from `main`
6. After edits, inspect `git status`
7. Verify only expected documentation files are included; exclude `Tasks` and unrelated files
8. Review the diff summary
9. Commit the intended files (message = Jira key)
10. Push the task branch
11. **Create the MR into `DEV`; return its link**
12. **Mirror the same changes to the working `main` branch; push; create the MR into `main`; return its link**
13. **Check conflicts against `DEV` and `main` separately**
14. Pass results to the orchestrator/`doc-writer` for the Jira comment

If the user said draft-only / don't push, stop after step 8 and report.

## Files typically allowed

- article `.md` files in `doc_diplo`
- `toc.yaml`
- new or updated article images in the documentation image tree

## Files typically not allowed

- anything under `Tasks`
- local drafts outside the repository
- unrelated config files
- environment files (`.env`)

## Conflict checks

- check conflict risk against **both** `DEV` and `main` before/after each MR
- diff against the base to verify task scope
- binary files (screenshots): identify, resolve explicitly, report which side was chosen
- if `DEV`/`main` diverged: separate branches per target (see rules.md)
