from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any, Dict

from config import AppConfig
from jira_client import JiraClient
from llm_client import LLMClient
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate release summary for a Jira issue using an LLM.",
    )
    parser.add_argument(
        "issue_key",
        nargs="?",
        help="Jira issue key (e.g. MSP-7906).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the summary along with the fetched Jira data as JSON.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Logging level (DEBUG, INFO, WARNING, ERROR). Overrides LOG_LEVEL from .env if set.",
    )
    return parser.parse_args()


def configure_logging(level_name: str | None) -> None:
    # Allow configuring via environment variable LOG_LEVEL when flag not provided
    effective_level = (level_name or os.getenv("LOG_LEVEL") or "INFO").upper()
    numeric_level = getattr(logging, effective_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    )


def read_issue_key(args: argparse.Namespace) -> str:
    issue_key = args.issue_key or os.getenv("JIRA_ISSUE_KEY")
    if issue_key:
        return issue_key

    issue_key = input("Enter Jira issue key: ").strip()
    if not issue_key:
        raise ValueError("Jira issue key is required")
    return issue_key


def build_issue_payload(issue_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": issue_data.get("title", ""),
        "description": issue_data.get("description", ""),
        "comments": issue_data.get("comments", []),
    }


def main() -> int:
    args = parse_args()
    # Load .env early so LOG_LEVEL and other vars are available
    load_dotenv()
    configure_logging(args.log_level)

    try:
        config = AppConfig.load()
    except Exception as exc:
        logging.error("Failed to load configuration: %s", exc)
        return 1

    try:
        issue_key = read_issue_key(args)
    except ValueError as exc:
        logging.error("%s", exc)
        return 1

    jira_client = JiraClient(
        base_url=config.jira_base_url,
        email=config.jira_email,
        api_token=config.jira_api_token,
        auth_type=config.jira_auth_type,
        api_version=config.jira_api_version,
        timeout=config.request_timeout,
    )

    try:
        issue_data = jira_client.get_issue_data(issue_key)
    except Exception as exc:
        logging.exception("Failed to fetch Jira issue data: %s", exc)
        return 1

    llm_client = LLMClient(
        endpoint=config.llm_endpoint,
        api_key=config.llm_api_key,
        model=config.llm_model,
        temperature=config.llm_temperature,
        max_tokens=config.llm_max_tokens,
        timeout=config.request_timeout,
        template_path=config.prompt_template_path,
    )

    try:
        payload = build_issue_payload(issue_data)
        summary = llm_client.generate_summary(payload)
    except Exception as exc:
        logging.exception("Failed to generate summary: %s", exc)
        return 1

    if args.json:
        output = {"issue": issue_key, "summary": summary, "source": payload}
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
