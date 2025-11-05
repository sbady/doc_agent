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


def generate_short_description(llm: LLMClient, payload: Dict[str, Any], template_path, system_prompt: Optional[str] = None) -> str:
    try:
        text = llm.generate_with_template(payload, template_path, system_prompt=system_prompt)
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
        short = generate_short_description(llm, issue_data, cfg.issue_short_template_path, system_prompt=cfg.issue_short_system_prompt)
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
        # Гиперссылка только на номер, название — текстом
        task_cell = f"[{it.key}|{it.url}] {escape_pipes(it.title)}"
        short_cell = sanitize_short_for_wiki(it.short)
        lines.append(f"|{task_cell}|{it.stand}|{it.kind}|-|-|{short_cell}|")
    return "\n".join(lines)


def escape_pipes(text: str) -> str:
    return (text or "").replace("|", "\\|")


def sanitize_short_for_wiki(text: str) -> str:
    """Sanitize short description for Jira wiki table cell.

    - Trim and strip wrapping quotes
    - Replace newlines with Jira hard breaks "\\\" (double backslash)
    - Escape pipe characters
    """
    t = (text or "").strip()
    # Remove surrounding quotes if present
    pairs = [("\"", "\""), ("“", "”"), ("«", "»")]
    for lq, rq in pairs:
        if t.startswith(lq) and t.endswith(rq):
            t = t[len(lq):-len(rq)].strip()
            break
    # Normalize newlines and replace with hard line breaks
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in t:
        parts = [p.strip() for p in t.split("\n") if p.strip()]
        # Jira wiki hard line break is two backslashes
        t = r" \\ ".join(parts)
    # Escape pipes
    t = escape_pipes(t)
    return t


def update_table_section(original: str, new_table: str) -> str:
    """Update only the table block under the specific h2 title without touching other content.

    - If h2 not found: append full new_table at the end.
    - If h2 found but no table header: insert table right after the h2 line.
    - If table found: replace only the table header + rows block, keep everything before/after.
    """
    header_re = re.compile(r"(?mi)^h2\.\s*Таблица релиза.*$")
    header_line = "||Задача||Стенд||Тип задачи||Шаблоны||Мануал||Краткое описание||"
    row_re = re.compile(r"^\|.*\|$")

    # Extract only the table block from provided new_table (drop its h2 if present)
    nt_lines = (new_table or "").splitlines()
    try:
        nt_start = nt_lines.index(header_line)
    except ValueError:
        # Fallback: find the first line starting with '||'
        nt_start = next((i for i, l in enumerate(nt_lines) if l.strip().startswith("||")), 0)
    new_block = nt_lines[nt_start:]

    if not header_re.search(original or ""):
        base = (original or "").rstrip()
        return f"{base}\n\n{new_table}\n"

    lines = (original or "").splitlines()
    # Locate the h2 header line
    h2_idx = next((i for i, ln in enumerate(lines) if header_re.match(ln)), None)
    if h2_idx is None:
        return (original or "") + "\n\n" + new_table + "\n"

    # Locate existing table header after h2
    tbl_hdr_idx = None
    for i in range(h2_idx + 1, len(lines)):
        if lines[i].strip() == header_line:
            tbl_hdr_idx = i
            break
        # stop early if another header encountered before table
        if lines[i].startswith("h2."):
            break

    if tbl_hdr_idx is None:
        # Insert new block after h2, keep the rest intact
        new_lines = lines[: h2_idx + 1] + new_block + lines[h2_idx + 1 :]
        return "\n".join(new_lines)

    # Find end of existing table: first non-row after header
    end = tbl_hdr_idx + 1
    while end < len(lines) and row_re.match(lines[end]):
        end += 1

    new_lines = lines[:tbl_hdr_idx] + new_block + lines[end:]
    return "\n".join(new_lines)


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
        # Split by unescaped pipes so escaped '\|' stay within a cell
        raw_cells = re.split(r"(?<!\\)\|", m.group(1))
        cells = [c.strip() for c in raw_cells]
        if not cells:
            continue
        # first cell contains link like [KEY Title|url]
        # Support both forms: [KEY|url] Title  and legacy [KEY Title|url]
        key_match = re.search(r"\[([A-Z][A-Z0-9]+-\d+)(?:[^\]]*?)\|", cells[0])
        if key_match:
            existing[key_match.group(1)] = cells

    # Produce new rows, preserving columns 4 and 5 when present
    out_lines = ["h2. Таблица релиза: в какие статьи нужно внести изменения", header_line]
    for it in sort_items(new_items):
        keep = existing.get(it.key)
        col4 = keep[3] if keep and len(keep) > 3 else "-"
        col5 = keep[4] if keep and len(keep) > 4 else "-"
        # Ссылка только на номер, название — текст
        task_cell = f"[{it.key}|{it.url}] {escape_pipes(it.title)}"
        short_cell = sanitize_short_for_wiki(it.short)
        out_lines.append(f"|{task_cell}|{it.stand}|{it.kind}|{col4}|{col5}|{short_cell}|")
    return "\n".join(out_lines)
