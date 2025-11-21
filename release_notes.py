from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from config import AppConfig
from jira_client import JiraClient
from llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class RNItem:
    key: str
    title: str
    url: str
    stand: str  # MS | WCE | Оба | Оба?
    kind: str   # Фича | Баг
    short: str  # краткое описание или "не описываем"


def fetch_related_issue_keys(jira: JiraClient, parent_key: str) -> List[str]:
    # Request issue with issuelinks field
    url = f"{jira._base_url}/rest/api/{jira._api_version or '3'}/issue/{parent_key}"
    params = {"fields": "issuelinks"}
    logger.info("Fetching related issues for %s", parent_key)
    resp = jira._session.get(url, params=params, timeout=jira._timeout)
    resp.raise_for_status()
    data = resp.json()
    links = data.get("fields", {}).get("issuelinks", []) or []
    keys: List[str] = []
    for link in links:
        ltype = (link.get("type") or {}).get("name")
        if ltype != "Relates":
            continue
        if "inwardIssue" in link:
            keys.append(link["inwardIssue"].get("key"))
        if "outwardIssue" in link:
            keys.append(link["outwardIssue"].get("key"))
    # De-duplicate and drop parent if present
    uniq = [k for k in dict.fromkeys([k for k in keys if k and k != parent_key])]
    logger.info("Found %d related issues (Relates)", len(uniq))
    return uniq


def extract_stand_from_description(description: str) -> Tuple[str, bool]:
    """Return (stand, had_field).

    - MS if contains Mashroom RU
    - WCE if contains We.Cloud
    - Оба if both present
    - Оба? if no explicit stand field/value found
    """
    text = description or ""
    if not text:
        return "Оба?", False
    # Heuristic: check presence of the label line or values anywhere
    has_label = re.search(r"стенд[ы]?:", text, flags=re.IGNORECASE) is not None
    has_ms = re.search(r"Mashroom\s*RU", text, flags=re.IGNORECASE) is not None
    has_wce = re.search(r"We\.Cloud", text, flags=re.IGNORECASE) is not None
    if has_ms and has_wce:
        return "Оба", has_label
    if has_ms:
        return "MS", has_label
    if has_wce:
        return "WCE", has_label
    # No recognizable value
    return ("Оба?" if not has_label else "Оба"), has_label


def map_issue_type_to_kind(issue_type_name: str) -> str:
    if not issue_type_name:
        return "Фича"
    name = issue_type_name.strip().lower()
    if name == "bug" or name == "баг":
        return "Баг"
    # Treat the rest as feature
    return "Фича"


def generate_short_description(llm: LLMClient, payload: Dict[str, Any], template_path) -> str:
    try:
        text = llm.generate_with_template(payload, template_path)
        return text.strip() or "не описываем"
    except Exception as exc:
        logger.error("LLM short description failed: %s", exc)
        return "не описываем"


def build_items(jira: JiraClient, llm: LLMClient, cfg: AppConfig, parent_key: str) -> List[RNItem]:
    related = fetch_related_issue_keys(jira, parent_key)
    items: List[RNItem] = []
    for key in related:
        try:
            raw = jira._session.get(
                f"{jira._base_url}/rest/api/{jira._api_version or '3'}/issue/{key}",
                params={"fields": "summary,description,comment,issuetype"},
                timeout=jira._timeout,
            )
            raw.raise_for_status()
            payload = raw.json()
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", key, exc)
            continue

        fields = payload.get("fields", {})
        issuetype = (fields.get("issuetype") or {}).get("name") or ""
        is_subtask = (fields.get("issuetype") or {}).get("subtask") is True
        if is_subtask:
            logger.debug("Skip sub-task %s", key)
            continue

        issue_data = jira.get_issue_data(key)
        stand, had_field = extract_stand_from_description(issue_data.get("description", ""))
        kind = map_issue_type_to_kind(issuetype)
        short = generate_short_description(llm, issue_data, cfg.issue_short_template_path)
        url = f"{jira._base_url}/browse/{key}"
        items.append(RNItem(key=key, title=issue_data.get("title", ""), url=url, stand=stand, kind=kind, short=short))

    return sort_items(items)


def sort_items(items: List[RNItem]) -> List[RNItem]:
    def group_order(stand: str) -> int:
        if stand == "MS":
            return 0
        if stand == "Оба" or stand == "Оба?":
            return 1
        return 2  # WCE and anything else

    def type_order(kind: str) -> int:
        return 0 if kind == "Фича" else 1

    return sorted(items, key=lambda x: (group_order(x.stand), type_order(x.kind), x.key))


def make_jira_table(items: List[RNItem]) -> str:
    lines = []
    lines.append("h2. Таблица релиза: в какие статьи нужно внести изменения")
    lines.append("||Задача||Стенд||Тип задачи||Шаблоны||Мануал||Краткое описание||")
    for it in items:
        task_cell = f"[{it.key} {escape_pipes(it.title)}|{it.url}]"
        lines.append(f"|{task_cell}|{it.stand}|{it.kind}|-|-|{escape_pipes(it.short)}|")
    return "\n".join(lines)


def escape_pipes(text: str) -> str:
    return (text or "").replace("|", "\\|")


def update_table_section(original: str, new_table: str) -> str:
    """Replace or insert the release table section headed by the specific h2 title."""
    header_re = re.compile(r"(?mi)^h2\.\s*Таблица релиза.*$")
    if not header_re.search(original or ""):
        # Append new table with a separating blank line
        base = (original or "").rstrip()
        return f"{base}\n\n{new_table}\n"

    # Find start of section and end (next h2 or end of text)
    lines = (original or "").splitlines()
    start = None
    for i, ln in enumerate(lines):
        if header_re.match(ln):
            start = i
            break
    if start is None:
        return (original or "") + "\n\n" + new_table + "\n"
    # Find end
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^h2\.\s*", lines[j]):
            end = j
            break
    new_lines = lines[:start] + new_table.splitlines() + lines[end:]
    return "\n".join(new_lines) + ("\n" if original.endswith("\n") else "")


def merge_rows_preserve_manual(current_desc: str, new_items: List[RNItem]) -> str:
    """If table exists, update/add rows per issue preserving columns 4 and 5.

    If no table exists, return a newly generated table.
    """
    header_line = "||Задача||Стенд||Тип задачи||Шаблоны||Мануал||Краткое описание||"
    if header_line not in (current_desc or ""):
        return make_jira_table(new_items)

    # Parse existing table rows
    pattern_row = re.compile(r"^\|(.*)\|$")
    lines = (current_desc or "").splitlines()
    # Find table block boundaries
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == header_line:
            start = i
            break
    if start is None:
        return make_jira_table(new_items)
    end = start + 1
    while end < len(lines) and pattern_row.match(lines[end]):
        end += 1

    # Build map from issue key to existing row cells
    existing: Dict[str, List[str]] = {}
    for i in range(start + 1, end):
        m = pattern_row.match(lines[i])
        if not m:
            continue
        raw_cells = m.group(1).split("|")
        cells = [c.strip() for c in raw_cells]
        if not cells:
            continue
        # first cell contains link like [KEY Title|url]
        key_match = re.search(r"\[([A-Z][A-Z0-9]+-\d+)[^\]]*\|", cells[0])
        if key_match:
            existing[key_match.group(1)] = cells

    # Produce new rows, preserving columns 4 and 5 when present
    out_lines = ["h2. Таблица релиза: в какие статьи нужно внести изменения", header_line]
    for it in sort_items(new_items):
        keep = existing.get(it.key)
        col4 = keep[3] if keep and len(keep) > 3 else "-"
        col5 = keep[4] if keep and len(keep) > 4 else "-"
        task_cell = f"[{it.key} {escape_pipes(it.title)}|{it.url}]"
        out_lines.append(f"|{task_cell}|{it.stand}|{it.kind}|{col4}|{col5}|{escape_pipes(it.short)}|")
    return "\n".join(out_lines)
