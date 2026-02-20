from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any, Dict
import re

from config import AppConfig
from jira_client import JiraClient
from llm_client import LLMClient
from dotenv import load_dotenv
from release_notes import (
    build_items,
    make_jira_table,
    update_table_section,
    merge_rows_preserve_manual,
    parse_existing_table,
    sanitize_issue_data,
    normalize_short_text,
    make_jira_table_from_items,
    load_glossary_text,
    map_issue_type_to_kind,
    select_issue_short_template,
    generate_short_description,
    update_release_table_generated_column,
    extract_release_table_text,
    upsert_judge_panel,
    extract_release_table_issue_keys,
    make_doc_changelog_from_description,
)
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
    parser.add_argument(
        "--issue-short",
        action="store_true",
        help="Сгенерировать одну строку для релиз-таблицы по указанной задаче и вывести в консоль.",
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
        choices=["view", "fill", "fill-preview", "compare", "changelog-preview", "refine-preview", "refine-apply"],
        default="view",
        help=(
            "Режим работы релиз-таблицы: view — вывод в консоль; fill — обновление таблицы; fill-preview — прогон без записи; "
            "compare — дописать сгенерированные формулировки под эталонами и добавить анализ LLM-судьи; "
            "changelog-preview — собрать готовый текст релизных заметок для вставки в исходный код документации; "
            "refine-preview — генерация предложений улучшений; refine-apply — обновление таблицы новыми текстами."
        ),
    )
    parser.add_argument(
        "--preview-path",
        default=None,
        help="Путь файла для режима fill-preview (файл будет создан или перезаписан).",
    )
    parser.add_argument(
        "--compare-mode",
        choices=["replace", "append"],
        default="replace",
        help="Как заполнять блоки '_Сгенерировано:_' в колонке 'Краткое описание': replace — заменять; append — сохранять историю с нумерацией.",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Для режима compare: не вызывать LLM-судью и не добавлять анализ под таблицей.",
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

    # One-issue short release note line (uses the same templates as release table generation)
    if args.issue_short:
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
        llm_client = LLMClient(
            endpoint=config.llm_endpoint,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.llm_temperature,
            max_tokens=config.issue_short_max_tokens or config.llm_max_tokens,
            timeout=config.request_timeout,
            template_path=config.issue_short_template_path or config.issue_short_feature_template_path,
        )

        try:
            issue_data = jira_client.get_issue_data(issue_key)
        except Exception as exc:
            logging.exception("Failed to fetch Jira issue data: %s", exc)
            return 1

        payload = sanitize_issue_data(issue_data, mode=config.sanitizer_mode)
        try:
            payload["glossary"] = load_glossary_text()
        except Exception:
            payload["glossary"] = ""

        kind = map_issue_type_to_kind(issue_data.get("issue_type", ""))
        template_path = select_issue_short_template(config, kind=kind)
        try:
            short = generate_short_description(
                llm_client,
                payload,
                template_path,
                system_prompt=config.issue_short_system_prompt,
            )
        except Exception as exc:
            logging.error("Failed to generate short description: %s", exc)
            return 1

        print(short)
        logging.info("Total prompt characters sent to LLM: %d", LLMClient.get_total_prompt_chars())
        return 0

    # Branch: release notes workflow (including refine modes)
    if args.release_parent or config.release_parent_key or args.mode in {"compare", "changelog-preview"} or args.mode.startswith("refine"):
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
            template_path=config.issue_short_template_path or config.issue_short_feature_template_path,
        )

        # --- view/fill/fill-preview workflow ---
        if args.mode in {"view", "fill", "fill-preview"}:
            if not parent_key:
                logging.error("Release parent key is required for %s mode (use --release-parent or RELEASE_PARENT_KEY)", args.mode)
                return 1
            try:
                items = build_items(jira_client, llm_client, config, parent_key)
            except Exception as exc:
                logging.exception("Failed to build release notes items: %s", exc)
                return 1

            table = make_jira_table(items)

            if args.mode == "view":
                print(table)
                return 0

            if args.mode == "fill-preview":
                preview_path = args.preview_path or os.path.join("docs", "release_fill_preview.md")
                os.makedirs(os.path.dirname(preview_path), exist_ok=True)
                with open(preview_path, "w", encoding="utf-8") as f:
                    for item in items:
                        f.write(f"{item.key} {item.title}:\n{item.short}\n\n")
                logging.info("Fill preview saved to %s", preview_path)
                logging.info("Total prompt characters sent to LLM: %d", LLMClient.get_total_prompt_chars())
                return 0

            target_key = args.release_target or config.target_issue_key
            if not target_key:
                logging.error("Target issue key is required in fill mode (use --release-target or TARGET_ISSUE_KEY)")
                return 1

            if "-" not in str(target_key) and parent_key and "-" in parent_key:
                project = parent_key.split("-", 1)[0]
                logging.info("Inferring target key from parent project: %s -> %s-%s", target_key, project, target_key)
                target_key = f"{project}-{target_key}"

            try:
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
            logging.info("Total prompt characters sent to LLM: %d", LLMClient.get_total_prompt_chars())
            return 0

        # --- changelog preview workflow ---
        if args.mode == "changelog-preview":
            target_key = args.release_target or config.target_issue_key
            if not target_key:
                logging.error("Target issue key is required for changelog-preview mode (use --release-target or TARGET_ISSUE_KEY)")
                return 1
            if "-" not in str(target_key):
                logging.error("For changelog-preview use full target issue key, e.g. MSP-8968.")
                return 1

            try:
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
                logging.error("Target issue description is not a wiki string (likely ADF). Changelog preview is not supported.")
                return 1

            changelog_text = make_doc_changelog_from_description(current_desc)
            if not changelog_text:
                logging.error("Release table not found or contains no parsable rows for changelog generation.")
                return 1

            print(changelog_text)
            return 0

        # --- compare workflow ---
        if args.mode == "compare":
            target_key = args.release_target or config.target_issue_key
            if not target_key:
                logging.error("Target issue key is required for compare mode (use --release-target or TARGET_ISSUE_KEY)")
                return 1
            if "-" not in str(target_key) and parent_key and "-" in parent_key:
                project = parent_key.split("-", 1)[0]
                logging.info("Inferring target key from parent project: %s -> %s-%s", target_key, project, target_key)
                target_key = f"{project}-{target_key}"

            try:
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
                logging.error("Target issue description is not a wiki string (likely ADF). Compare is not supported.")
                return 1

            table_keys_ordered = extract_release_table_issue_keys(current_desc)
            if not table_keys_ordered:
                logging.error("Release table not found or has no parsable rows in target issue description.")
                return 1
            keys_to_generate = table_keys_ordered
            logging.info("Compare: table_keys=%d (generating only for table rows)", len(keys_to_generate))

            glossary_text = ""
            try:
                glossary_text = load_glossary_text()
            except Exception:
                glossary_text = ""

            generated_by_key: Dict[str, str] = {}
            for key in keys_to_generate:
                try:
                    issue_data = jira_client.get_issue_data(key)
                except Exception as exc:
                    logging.error("Skip %s: failed to fetch issue data: %s", key, exc)
                    continue
                sanitized = sanitize_issue_data(issue_data, mode=config.sanitizer_mode)
                sanitized["glossary"] = glossary_text
                kind = map_issue_type_to_kind(issue_data.get("issue_type", ""))
                template_path = select_issue_short_template(config, kind=kind)
                try:
                    short = generate_short_description(
                        llm_client,
                        sanitized,
                        template_path,
                        system_prompt=config.issue_short_system_prompt,
                    )
                except Exception as exc:
                    logging.error("Skip %s: failed to generate short: %s", key, exc)
                    continue
                generated_by_key[key] = short

            updated_desc, updated_rows, run_index = update_release_table_generated_column(
                current_desc,
                generated_by_key=generated_by_key,
                mode=args.compare_mode,
            )
            if updated_rows == 0:
                logging.warning("No matching rows updated (table missing or no intersecting issue keys).")

            judge_report = ""
            if not args.skip_judge:
                table_text = extract_release_table_text(updated_desc)
                if not table_text:
                    logging.error("Release table not found in target issue description; cannot run judge.")
                    return 1

                judge_prompt_path = os.getenv("JUDGE_PROMPT_PATH") or "prompt_templates/judge_release_table.txt"
                judge_prompt_path = AppConfig._resolve_path(judge_prompt_path)  # type: ignore[attr-defined]
                judge_system_prompt = os.getenv("JUDGE_SYSTEM_PROMPT") or None
                judge_max_tokens_env = os.getenv("JUDGE_MAX_TOKENS") or ""
                judge_max_tokens = None
                if judge_max_tokens_env.strip():
                    try:
                        judge_max_tokens = int(judge_max_tokens_env.strip())
                    except Exception:
                        judge_max_tokens = None

                judge_client = LLMClient(
                    endpoint=config.llm_endpoint,
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    temperature=min(config.llm_temperature, 0.2),
                    max_tokens=judge_max_tokens or (config.llm_max_tokens or 800),
                    timeout=config.request_timeout,
                    template_path=judge_prompt_path,
                )
                try:
                    judge_report = judge_client.generate_with_template(
                        {"table": table_text},
                        judge_prompt_path,
                        system_prompt=judge_system_prompt,
                    )
                    judge_report = (judge_report or "").strip()
                except Exception as exc:
                    logging.error("Judge LLM failed: %s", exc)
                    judge_report = (
                        "LLM‑судья не смог выполнить оценку (ошибка/таймаут).\n"
                        "Попробуйте увеличить REQUEST_TIMEOUT или запустить с --skip-judge."
                    )

            # Always update the table in description; judge output goes to a comment.
            try:
                jira_client.update_issue_description(target_key, updated_desc)
            except Exception:
                return 1

            if judge_report:
                title = "Оценка соответствия (LLM)"
                if args.compare_mode == "append" and run_index:
                    title = f"{title} #{run_index}"
                comment_body = f"h3. {title}\n\n{judge_report.strip()}\n"
                try:
                    jira_client.add_issue_comment(target_key, comment_body)
                except Exception as exc:
                    logging.error("Failed to add judge comment to %s: %s", target_key, exc)

            logging.info("Compare applied to %s: updated_rows=%d, mode=%s, run_index=%s", target_key, updated_rows, args.compare_mode, run_index)
            logging.info("Total prompt characters sent to LLM: %d", LLMClient.get_total_prompt_chars())
            return 0

        # --- refine workflow ---
        target_key = args.release_target or config.target_issue_key
        if not target_key:
            logging.error("Target issue key is required for refine modes (use --release-target or TARGET_ISSUE_KEY)")
            return 1
        if "-" not in str(target_key) and parent_key and "-" in parent_key:
            project = parent_key.split("-", 1)[0]
            logging.info("Inferring target key from parent project: %s -> %s-%s", target_key, project, target_key)
            target_key = f"{project}-{target_key}"

        try:
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
            logging.error("Target issue description is not a wiki string (likely ADF). Refine is not supported.")
            return 1

        existing_items = parse_existing_table(current_desc)
        if not existing_items:
            logging.error("No existing release table found to refine.")
            return 1

        glossary_text = ""
        try:
            glossary_text = load_glossary_text()
        except Exception:
            glossary_text = ""

        refine_client = LLMClient(
            endpoint=config.llm_endpoint,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.llm_temperature,
            max_tokens=config.refine_max_tokens or config.llm_max_tokens,
            timeout=config.request_timeout,
            template_path=config.refine_prompt_path,
        )

        refined: list[tuple[str, str, str]] = []  # (key, old, new)

        for item in existing_items:
            # Fast path: do not send "Не описываем" to LLM
            if item.short.strip().lower() == "не описываем":
                refined.append((item.key, item.short, item.short))
                continue
            try:
                issue_data = jira_client.get_issue_data(item.key)
            except Exception as exc:
                logging.error("Skip %s: failed to fetch issue data: %s", item.key, exc)
                refined.append((item.key, item.short, item.short))
                continue
            sanitized = sanitize_issue_data(issue_data, mode=config.sanitizer_mode)
            payload = {
                "draft": item.short,
                "glossary": glossary_text,
            }
            try:
                new_short = refine_client.generate_with_template(
                    payload,
                    config.refine_prompt_path,
                    system_prompt=config.refine_system_prompt,
                )
                new_short = normalize_short_text(new_short)
                if not new_short:
                    new_short = item.short
                # Guard: don't degrade meaningful drafts
                if new_short.strip().lower() == "не описываем" and item.short.strip().lower() != "не описываем":
                    new_short = item.short
                if len(new_short) > 220:
                    new_short = item.short
            except Exception as exc:
                logging.error("Refine failed for %s: %s", item.key, exc)
                new_short = item.short
            refined.append((item.key, item.short, new_short))

        if args.mode == "refine-preview":
            preview_path = os.path.join("docs", "release_refine_preview.md")
            os.makedirs(os.path.dirname(preview_path), exist_ok=True)
            with open(preview_path, "w", encoding="utf-8") as f:
                for idx, (key, old, new) in enumerate(refined, 1):
                    f.write(f"{idx}) {key}\nOLD: {old}\nNEW: {new}\n----\n")
            logging.info("Refine preview saved to %s", preview_path)
            return 0

        # apply
        updated_items = []
        new_map = {key: new for key, _, new in refined}
        for item in existing_items:
            updated_items.append(
                type(item)(
                    key=item.key,
                    title=item.title,
                    url=item.url,
                    stand=item.stand,
                    kind=item.kind,
                    short=new_map.get(item.key, item.short),
                )
            )

        new_table = make_jira_table_from_items(updated_items, preserve_order=True)
        new_desc = update_table_section(current_desc, new_table)
        try:
            jira_client.update_issue_description(target_key, new_desc)
        except Exception:
            return 1
        logging.info("Applied refined descriptions to %s", target_key)
        logging.info("Total prompt characters sent to LLM: %d", LLMClient.get_total_prompt_chars())
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
        if not config.prompt_template_path.exists():
            raise FileNotFoundError(
                f"Prompt template not found: {config.prompt_template_path} (set PROMPT_TEMPLATE_PATH in .env)"
            )
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

    logging.info("Total prompt characters sent to LLM: %d", LLMClient.get_total_prompt_chars())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
