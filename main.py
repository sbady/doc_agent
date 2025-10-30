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
from release_notes import build_items, make_jira_table, update_table_section, merge_rows_preserve_manual
import requests


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
    # Release notes workflow args
    parser.add_argument(
        "--release-parent",
        help="Ключ родительской релизной задачи (например, MSP-7288). Если задан, запускается режим релиз-таблицы.",
    )
    parser.add_argument(
        "--release-target",
        help="Ключ целевой задачи для заполнения таблицы (режим fill). Может быть также задан через TARGET_ISSUE_KEY.",
    )
    parser.add_argument(
        "--mode",
        choices=["view", "fill"],
        default="view",
        help="Режим работы релиз-таблицы: view — вывод в консоль; fill — обновление таблицы в целевой задаче.",
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

    # Branch: release notes workflow
    if args.release_parent or config.release_parent_key:
        parent_key = args.release_parent or config.release_parent_key
        jira_client = JiraClient(
            base_url=config.jira_base_url,
            email=config.jira_email,
            api_token=config.jira_api_token,
            auth_type=config.jira_auth_type,
            api_version=config.jira_api_version,
            timeout=config.request_timeout,
        )
        llm_client = LLMClient(
            endpoint=config.llm_endpoint,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.llm_temperature,
            max_tokens=config.issue_short_max_tokens or config.llm_max_tokens,
            timeout=config.request_timeout,
            template_path=config.issue_short_template_path,
        )
        try:
            items = build_items(jira_client, llm_client, config, parent_key)
        except Exception as exc:
            logging.exception("Failed to build release notes items: %s", exc)
            return 1

        table = make_jira_table(items)

        if args.mode == "view":
            print(table)
            return 0

        # mode == fill
        target_key = args.release_target or config.target_issue_key
        if not target_key:
            logging.error("Target issue key is required in fill mode (use --release-target or TARGET_ISSUE_KEY)")
            return 1

        # If a numeric ID (e.g., "7382") is provided, infer project key from parent (e.g., MSP-7382)
        if "-" not in str(target_key) and parent_key and "-" in parent_key:
            project = parent_key.split("-", 1)[0]
            logging.info("Inferring target key from parent project: %s -> %s-%s", target_key, project, target_key)
            target_key = f"{project}-{target_key}"

        # Fetch current description to perform idempotent merge/update
        try:
            # Read raw description string via authenticated session
            url = f"{config.jira_base_url.rstrip('/')}/rest/api/{config.jira_api_version or '3'}/issue/{target_key}"
            params = {"fields": "description"}
            r2 = jira_client._session.get(url, params=params, timeout=config.request_timeout)
            r2.raise_for_status()
            target_payload = r2.json()
        except Exception as exc:
            logging.exception("Failed to fetch target issue %s: %s", target_key, exc)
            return 1

        current_desc = target_payload.get("fields", {}).get("description")
        if not isinstance(current_desc, str):
            logging.error("Target issue description is not a wiki string (likely ADF). Automatic fill is not supported.")
            print(table)
            return 1

        merged_table = merge_rows_preserve_manual(current_desc, items)
        new_desc = update_table_section(current_desc, merged_table)

        try:
            jira_client.update_issue_description(target_key, new_desc)
        except Exception:
            return 1

        logging.info("Updated release table in %s", target_key)
        return 0

    # Default branch: single issue summary (existing behavior)
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
