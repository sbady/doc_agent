# Changelog

## v0.1 — Initial release

- Fetches Jira issue data (summary, description, comments) with PAT/basic auth and API version selection.
- Renders a Jinja2 prompt from template `prompt_templates/release_summary.txt`.
- Calls local OpenAI-compatible LLM endpoint; supports `/v1/chat/completions` payload shape.
- Improved error handling and logging with previews and raw response snippets.
- LOG_LEVEL configurable via `.env` with CLI flag override `--log-level`.
- Added `.gitignore` for Python, venv, and local env files.

