from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from config import AppConfig
from jira_client import JiraClient
from llm_client import LLMClient

logger = logging.getLogger(__name__)

RELEASE_TABLE_HEADER_LINE = "||Задача||Стенд||Тип задачи||Шаблоны||Мануал||Краткое описание||"
_TABLE_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")


# ----------------------------
# Data model
# ----------------------------

@dataclass
class RNItem:
    key: str
    title: str
    url: str
    stand: str  # MS | WCE | Оба | Оба?
    kind: str   # Фича | Баг
    short: str  # краткое описание или "не описываем"


# ----------------------------
# Helpers: classification
# ----------------------------

def extract_stand_from_description(description: str) -> Tuple[str, bool]:
    """Return (stand, had_field) based on a dedicated block or keywords."""
    text = description or ""
    if not text:
        return "Оба?", False
    # Try to find explicit block "h3. *Стенды:*" then read the next line
    lines = text.splitlines()
    stand_line = None
    for idx, line in enumerate(lines):
        if re.search(r"h3\.\s*\*?Стенды\*?:?", line, flags=re.IGNORECASE):
            if idx + 1 < len(lines):
                stand_line = lines[idx + 1]
            break
    if stand_line:
        has_label = True
        has_ms = re.search(r"Mashroom", stand_line, flags=re.IGNORECASE) is not None
        has_wce = re.search(r"We\.Cloud", stand_line, flags=re.IGNORECASE) is not None
    else:
        has_label = re.search(r"стенд[ы]?:", text, flags=re.IGNORECASE) is not None
        has_ms = re.search(r"Mashroom", text, flags=re.IGNORECASE) is not None
        has_wce = re.search(r"We\.Cloud", text, flags=re.IGNORECASE) is not None
    if has_ms and has_wce:
        return "Оба", has_label
    if has_ms:
        return "MS", has_label
    if has_wce:
        return "WCE", has_label
    return ("Оба?" if not has_label else "Оба"), has_label


def map_issue_type_to_kind(issue_type_name: str) -> str:
    if not issue_type_name:
        return "Фича"
    name = issue_type_name.strip().lower()
    if name in {"bug", "баг", "ошибка", "error", "problem"}:
        return "Баг"
    return "Фича"


# ----------------------------
# Helpers: sanitization
# ----------------------------

_URL_PATTERN = re.compile(r"https?://[^\s)>\]]+")
_HOST_PATTERN = re.compile(
    r"\b[\w.-]+\.(?:local|internal|lan|mashroom\.online|pikemedia\.live|pikemedia\.ru|gitlab[\w.-]*|dev|test)\b",
    flags=re.IGNORECASE,
)


def _strip_url(url: str) -> str:
    """Keep scheme+host+path, drop query/fragment."""
    # simple split on ? and #
    for sep in ("?", "#"):
        if sep in url:
            url = url.split(sep, 1)[0]
    return url


def _scrub_logs_strict(t: str) -> str:
    """Hard scrub server/request/upstream/host and log-like lines."""
    lines = []
    for line in t.splitlines():
        low = line.lower()
        if (
            "request:" in low
            or "upstream" in low
            or "server:" in low
            or "host:" in low
            or re.search(r"\b(get|post|put|delete|patch)\s+/[^\s]*\s+http/\d", low)
        ):
            lines.append("<redacted_log>")
            continue
        lines.append(line)
    t = "\n".join(lines)
    # Remove remaining server/request/upstream/host fragments if any
    t = re.sub(r"(?i)(server|request|upstream|host)\s*:[^,\n]+", r"\1:<redacted>", t)
    return t


def clean_text(text: Any, *, mode: str = "strict") -> str:
    """Mask sensitive tokens; mode 'strict' removes logs/hosts more aggressively."""
    if text is None:
        return ""
    t = str(text)
    # Drop inline Jira images/attachments like !image.png|thumbnail!
    t = re.sub(r"!.*?!", "", t)
    # Mask obvious secrets/tokens
    t = re.sub(r"(?i)(token|secret|password|passwd|pass|key)\s*[:=]\s*[\w\-]{4,}", r"\1=<redacted>", t)
    t = re.sub(r"sk-[A-Za-z0-9]{12,}", "<redacted>", t)
    # Mask Authorization headers (Basic/Bearer) including inline curl examples
    t = re.sub(r"(?i)Authorization:\s*Basic\s+[A-Za-z0-9+/=]+", "Authorization: Basic <redacted>", t)
    t = re.sub(r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9._\-+/=]+", "Authorization: Bearer <redacted>", t)
    # Mask long base64-ish tokens after Basic even without header word
    t = re.sub(r"(?i)Basic\s+[A-Za-z0-9+/=]{8,}", "Basic <redacted>", t)
    # Mask long hex/base64-like chunks (>=20 chars) often used as tokens/keys
    t = re.sub(r"\b[A-Za-z0-9+/=]{20,}\b", "<redacted_id>", t)
    # Mask emails / phones / IPs
    t = re.sub(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<redacted_email>", t)
    t = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<redacted_ip>", t)
    # Strip query from URLs but keep domain/path
    t = _URL_PATTERN.sub(lambda m: _strip_url(m.group(0)), t)

    # Mask explicit merge_request/issue ids early to avoid phone-regex collisions
    t = re.sub(r"(?i)(merge_requests|issues)/\d+", r"\1/<redacted_id>", t)

    if mode == "strict":
        # Remove internal hosts and gitlab/dev/test domains
        t = _HOST_PATTERN.sub("<redacted_host>", t)
        # Mask id-like params
        t = re.sub(
            r"(?i)(viewerid|activityid|browserid|conferenceid|token|key|hash)=([A-Za-z0-9\-]+)",
            lambda m: f"{m.group(1)}=<redacted_id>",
            t,
        )
        # Remove code blocks (SQL / curl etc.)
        t = re.sub(r"\{code[:\w]*\}.*?\{code\}", "<redacted_code>", t, flags=re.DOTALL | re.IGNORECASE)
        t = re.sub(r"```.*?```", "<redacted_code>", t, flags=re.DOTALL)
        # Scrub log lines/server/request/upstream
        t = _scrub_logs_strict(t)

    # Phone: exclude dotted version-like patterns and numeric URL tails already masked
    t = re.sub(r"\b\+?\d[\d\s()/-]{6,}\b", "<redacted_phone>", t)
    # Limit very long blobs
    if len(t) > 6000:
        t = t[:6000] + " <truncated>"
    return t.strip()


def sanitize_issue_data(issue: Dict[str, Any], mode: str = "strict") -> Dict[str, Any]:
    return {
        "title": clean_text(issue.get("title", ""), mode=mode),
        "description": clean_text(issue.get("description", ""), mode=mode),
        "comments": [clean_text(c, mode=mode) for c in issue.get("comments", [])],
        "issue_type": clean_text(issue.get("issue_type", ""), mode=mode),
    }


def load_glossary_text() -> str:
    """Read glossary terms if present (docs/glossary/TERMS.md)."""
    from pathlib import Path

    path = Path(__file__).resolve().parent / "docs" / "glossary" / "TERMS.md"
    try:
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            return content
    except Exception:
        return ""
    return ""


def normalize_short_text(text: str) -> str:
    """Collapse whitespace/quotes and trim trailing punctuation."""
    if text is None:
        return ""
    t = str(text).replace("\r", " ")
    # Drop meta prefixes sometimes returned by chat models
    t = re.sub(r"(?i)^(?:вывод|ответ|результат|final answer|result)\s*:\s*", "", t).strip()
    # Normalize common "1-1" phrasing for chats
    t = re.sub(r"\b1\s*[-–—]\s*1\b", "1 на 1", t)
    replacements = {
        "«": '"', "»": '"',
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "‘": '"', "’": '"', "‚": '"', "‹": '"', "›": '"',
    }
    for src, dst in replacements.items():
        t = t.replace(src, dst)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r'(["]?)\s*(?:\.{1,3}|…)\s*$', r"\1", t)
    t = t.strip()
    # Cut off excessive length to avoid spilling into reasoning
    if len(t) > 220:
        t = t[:220].rstrip()
    return t


# ----------------------------
# Core flow
# ----------------------------

def generate_short_description(llm: LLMClient, payload: Dict[str, Any], template_path, system_prompt: Optional[str] = None) -> str:
    try:
        text = llm.generate_with_template(payload, template_path, system_prompt=system_prompt)
        return normalize_short_text(text) or "не описываем"
    except Exception as exc:
        logger.error("LLM short description failed: %s", exc)
        return "не описываем"


def select_issue_short_template(cfg: AppConfig, *, kind: str) -> Any:
    """Select short-description template for the release table."""
    # Backward-compatible override: single template for both kinds.
    if getattr(cfg, "issue_short_template_path", None):
        return cfg.issue_short_template_path
    if kind == "Баг":
        return cfg.issue_short_bug_template_path
    return cfg.issue_short_feature_template_path


def fetch_related_issue_keys(jira: JiraClient, parent_key: str) -> List[str]:
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
    uniq = [k for k in dict.fromkeys([k for k in keys if k and k != parent_key])]
    logger.info("Found %d related issues (Relates)", len(uniq))
    return uniq


def build_items(jira: JiraClient, llm: LLMClient, cfg: AppConfig, parent_key: str) -> List[RNItem]:
    related = fetch_related_issue_keys(jira, parent_key)
    items: List[RNItem] = []
    glossary_text = load_glossary_text()
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
        sanitized_issue = sanitize_issue_data(issue_data, mode=getattr(cfg, "sanitizer_mode", "strict"))
        sanitized_issue["glossary"] = glossary_text
        stand, _ = extract_stand_from_description(issue_data.get("description", ""))
        kind = map_issue_type_to_kind(issuetype)
        short_template = select_issue_short_template(cfg, kind=kind)
        short = generate_short_description(llm, sanitized_issue, short_template, system_prompt=cfg.issue_short_system_prompt)

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


# ----------------------------
# Table rendering
# ----------------------------

def make_jira_table(items: List[RNItem]) -> str:
    return make_jira_table_from_items(items, preserve_order=False)


def make_jira_table_from_items(items: List[RNItem], preserve_order: bool = False) -> str:
    lines = []
    lines.append("h2. Таблица релиза: в какие статьи нужно внести изменения")
    lines.append("||Задача||Стенд||Тип задачи||Шаблоны||Мануал||Краткое описание||")
    ordered = items if preserve_order else sort_items(items)
    for it in ordered:
        task_cell = f"[{it.key}|{it.url}] {escape_pipes(it.title)}"
        lines.append(f"|{task_cell}|{it.stand}|{it.kind}|-|-|{escape_pipes(it.short)}|")
    return "\n".join(lines)


def escape_pipes(text: str) -> str:
    return (text or "").replace("|", "\\|")


def update_table_section(original: str, new_table: str) -> str:
    """Replace or insert the release table section headed by the specific h2 title."""
    header_re = re.compile(r"(?mi)^h2\.\s*Таблица релиза.*$")
    if not header_re.search(original or ""):
        base = (original or "").rstrip()
        return f"{base}\n\n{new_table}\n"

    lines = (original or "").splitlines()
    start = None
    for i, ln in enumerate(lines):
        if header_re.match(ln):
            start = i
            break
    if start is None:
        return (original or "") + "\n\n" + new_table + "\n"

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

    pattern_row = re.compile(r"^\|(.*)\|$")
    lines = (current_desc or "").splitlines()
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

    existing: Dict[str, List[str]] = {}
    for i in range(start + 1, end):
        m = pattern_row.match(lines[i])
        if not m:
            continue
        raw_cells = m.group(1).split("|")
        cells = [c.strip() for c in raw_cells]
        if not cells:
            continue
        key_match = re.search(r"\[([A-Z][A-Z0-9]+-\d+)[^\]]*\|", cells[0])
        if key_match:
            existing[key_match.group(1)] = cells

    out_lines = ["h2. Таблица релиза: в какие статьи нужно внести изменения", header_line]
    for it in sort_items(new_items):
        keep = existing.get(it.key)
        col4 = keep[3] if keep and len(keep) > 3 else "-"
        col5 = keep[4] if keep and len(keep) > 4 else "-"
        task_cell = f"[{it.key}|{it.url}] {escape_pipes(it.title)}"
        out_lines.append(f"|{task_cell}|{it.stand}|{it.kind}|{col4}|{col5}|{escape_pipes(it.short)}|")
    return "\n".join(out_lines)


def parse_existing_table(current_desc: str) -> List[RNItem]:
    """Parse existing release table rows from description into RNItem list (keep order)."""
    header_re = re.compile(r"\|\|.*Задача.*Краткое\s+описание.*\|\|", flags=re.IGNORECASE)
    if not header_re.search(current_desc or ""):
        logger.debug("parse_existing_table: header not found in description (len=%d)", len(current_desc or ""))
        return []
    pattern_row = re.compile(r"^\|(.*)\|$")
    lines = (current_desc or "").splitlines()
    start = None
    for i, ln in enumerate(lines):
        if header_re.search(ln.strip()):
            start = i
            break
    if start is None:
        logger.debug("parse_existing_table: header line index not found")
        return []
    end = start + 1
    while end < len(lines) and pattern_row.match(lines[end]):
        end += 1

    items: List[RNItem] = []
    for i in range(start + 1, end):
        m = pattern_row.match(lines[i])
        if not m:
            continue
        raw = m.group(1)
        # Split by '|' that are not inside [...] to keep link intact
        raw_cells = re.split(r"\|(?![^\[]*\])", raw)
        cells = [c.strip() for c in raw_cells]
        if not cells or len(cells) < 6:
            continue
        # first cell format: [KEY|url] Title
        key_match = re.search(r"\[([A-Z][A-Z0-9]+-\d+)\|([^\]]+)\]\s*(.*)", cells[0])
        if not key_match:
            continue
        key = key_match.group(1)
        url = key_match.group(2)
        title = key_match.group(3).strip()
        stand = cells[1] if len(cells) > 1 else ""
        kind = cells[2] if len(cells) > 2 else ""
        short = cells[5] if len(cells) > 5 else ""
        items.append(RNItem(key=key, title=title, url=url, stand=stand, kind=kind, short=short))
    return items


def _split_table_row_cells(raw: str) -> List[str]:
    # Split by unescaped pipes that are not inside [...] (to keep Jira link intact).
    return re.split(r"(?<!\\)\|(?![^\[]*\])", raw)


def _collect_table_rows(lines: List[str], start_idx: int) -> tuple[List[tuple[int, int, str]], int]:
    """Collect wiki table rows starting at start_idx (header_idx + 1).

    Supports rows that span multiple physical lines until a line ending with '|'. Returns:
    - rows: list of (start_line_idx, end_line_idx_exclusive, row_text_with_newlines)
    - end_idx: first line index after the table rows
    """
    rows: List[tuple[int, int, str]] = []
    i = start_idx
    in_row = False
    row_start = -1
    buf: List[str] = []

    while i < len(lines):
        ln = lines[i]
        if not in_row:
            if ln.lstrip().startswith("|"):
                in_row = True
                row_start = i
                buf = [ln]
                if ln.rstrip().endswith("|"):
                    rows.append((row_start, i + 1, "\n".join(buf)))
                    in_row = False
                    buf = []
                    row_start = -1
                i += 1
                continue
            break

        # continuation line inside a multi-line row
        if i != row_start:
            buf.append(ln)
        if ln.rstrip().endswith("|"):
            rows.append((row_start, i + 1, "\n".join(buf)))
            in_row = False
            buf = []
            row_start = -1
        i += 1

    # If the row is unterminated, we ignore it (table is malformed).
    return rows, i


def _row_text_to_cells(row_text: str) -> List[str]:
    raw = re.sub(r"^\s*\|", "", row_text, count=1)
    raw = re.sub(r"\|\s*$", "", raw)
    return [c.strip() for c in _split_table_row_cells(raw)]


def _cells_to_single_line_row(cells: List[str]) -> str:
    # Encode line breaks inside cells as '\\\\' so the table stays stable.
    normalized = [(c or "").replace("\r", "").replace("\n", "\\\\").strip() for c in cells]
    return "|" + "|".join(normalized) + "|"


def _extract_issue_key_from_task_cell(cell: str) -> Optional[str]:
    m = re.search(r"\[([A-Z][A-Z0-9]+-\d+)\|", cell or "")
    return m.group(1) if m else None


def _next_generated_index(existing_short: str) -> int:
    # Find max N in "_Сгенерировано #N:_" blocks; also treat unnumbered as N=1.
    if not existing_short:
        return 1
    nums = [int(x) for x in re.findall(r"_Сгенерировано\s*#(\d+)\s*:_", existing_short)]
    if re.search(r"_Сгенерировано\s*:_", existing_short):
        nums.append(1)
    return (max(nums) + 1) if nums else 1


def append_generated_to_short_cell(
    existing_short: str,
    generated_short: str,
    *,
    mode: str,
    run_index: Optional[int] = None,
) -> str:
    """Append/replace generated text under the baseline in a Jira table cell.

    The cell content must stay a single line; line breaks inside a Jira table cell are encoded as '\\\\'.
    """
    # Prefer human-readable newlines in the cell. Also normalize past runs that used '\\\\' as a line-break marker.
    baseline = (existing_short or "").replace("\\\\", "\n").strip()
    gen = (generated_short or "").strip()
    if not gen:
        return baseline

    if mode not in {"replace", "append"}:
        raise ValueError("mode must be 'replace' or 'append'")

    if mode == "replace":
        # Keep everything before the first generated marker, if present.
        marker = re.search(r"(?:^|\n)_Сгенерировано(?:\s*#\d+)?\s*:_", baseline)
        if marker:
            baseline = baseline[: marker.start()].rstrip()
        label = "_Сгенерировано:_"
        return f"{baseline}\n{label}\n{gen}".strip() if baseline else f"{label}\n{gen}".strip()

    # append
    idx = run_index if run_index is not None else _next_generated_index(baseline)
    label = f"_Сгенерировано #{idx}:_"
    if not baseline:
        return f"{label}\n{gen}".strip()
    return f"{baseline}\n{label}\n{gen}".strip()


def update_release_table_generated_column(
    current_desc: str,
    *,
    generated_by_key: Dict[str, str],
    mode: str,
) -> tuple[str, int, Optional[int]]:
    """Update only 'Краткое описание' column for existing rows; never adds new rows.

    Returns (new_description, updated_rows_count, run_index_if_append).
    """
    lines = (current_desc or "").splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == RELEASE_TABLE_HEADER_LINE:
            header_idx = i
            break
    if header_idx is None:
        return current_desc or "", 0, None

    rows, table_end_idx = _collect_table_rows(lines, header_idx + 1)

    # In append mode, use one global run index across all rows.
    run_index: Optional[int] = None
    if mode == "append":
        max_existing = 0
        for _, _, row_text in rows:
            cells = _row_text_to_cells(row_text)
            if len(cells) < 6:
                continue
            existing_short = (cells[5] or "").replace("\n", "\\\\")
            next_i = _next_generated_index(existing_short)
            max_existing = max(max_existing, next_i - 1)
        run_index = max_existing + 1

    updated = 0
    new_row_blocks: List[str] = []
    for _, _, row_text in rows:
        cells = _row_text_to_cells(row_text)
        if len(cells) < 6:
            new_row_blocks.append(row_text.rstrip("\n"))
            continue
        key = _extract_issue_key_from_task_cell(cells[0])
        if not key or key not in generated_by_key:
            new_row_blocks.append(row_text.rstrip("\n"))
            continue
        cells[5] = append_generated_to_short_cell(
            cells[5],
            generated_by_key[key],
            mode=mode,
            run_index=run_index,
        )
        new_row_blocks.append(("|" + "|".join(cells) + "|").rstrip("\n"))
        updated += 1

    out_lines = lines[: header_idx + 1] + new_row_blocks + lines[table_end_idx:]
    return "\n".join(out_lines) + ("\n" if (current_desc or "").endswith("\n") else ""), updated, run_index


def extract_release_table_issue_keys(desc: str) -> List[str]:
    """Return keys present in the release table rows (order preserved)."""
    lines = (desc or "").splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == RELEASE_TABLE_HEADER_LINE:
            header_idx = i
            break
    if header_idx is None:
        return []
    rows, _ = _collect_table_rows(lines, header_idx + 1)
    keys: List[str] = []
    for _, _, row_text in rows:
        cells = _row_text_to_cells(row_text)
        if not cells:
            continue
        k = _extract_issue_key_from_task_cell(cells[0])
        if k:
            keys.append(k)
    return list(dict.fromkeys(keys))


def extract_release_table_text(desc: str) -> str:
    """Extract just the release table (header + rows) from a wiki description."""
    lines = (desc or "").splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == RELEASE_TABLE_HEADER_LINE:
            header_idx = i
            break
    if header_idx is None:
        return ""
    _, table_end_idx = _collect_table_rows(lines, header_idx + 1)
    # Include the h2 heading line if present directly above.
    start = header_idx
    if header_idx > 0 and re.match(r"(?mi)^h2\.\s*Таблица релиза", lines[header_idx - 1] or ""):
        start = header_idx - 1
    return "\n".join(lines[start:table_end_idx]).strip()


def upsert_judge_panel(desc: str, report_text: str, *, mode: str, run_index: Optional[int]) -> str:
    """Insert judge report under the release table as a Jira wiki panel."""
    if not report_text:
        return desc or ""

    title = "Оценка соответствия (LLM)"
    if mode == "append" and run_index:
        title = f"{title} #{run_index}"

    panel_start = f"{{panel:title={title}}}"
    panel_end = "{panel}"

    lines = (desc or "").splitlines()
    # Find table end to insert right below.
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == RELEASE_TABLE_HEADER_LINE:
            header_idx = i
            break
    if header_idx is None:
        # No table: append at end.
        base = (desc or "").rstrip()
        return f"{base}\n\n{panel_start}\n{report_text.strip()}\n{panel_end}\n"

    _, row_end = _collect_table_rows(lines, header_idx + 1)

    # replace mode: remove existing panels with the same base title (any #N)
    new_lines = list(lines)
    if mode == "replace":
        base_title_prefix = "{panel:title=Оценка соответствия (LLM)"
        i = 0
        while i < len(new_lines):
            if new_lines[i].startswith(base_title_prefix):
                # remove until closing {panel}
                j = i + 1
                while j < len(new_lines) and new_lines[j].strip() != panel_end:
                    j += 1
                if j < len(new_lines):
                    j += 1
                del new_lines[i:j]
                continue
            i += 1

        # Recompute insertion point after deletion
        header_idx2 = None
        for k, ln in enumerate(new_lines):
            if ln.strip() == RELEASE_TABLE_HEADER_LINE:
                header_idx2 = k
                break
        if header_idx2 is None:
            base = "\n".join(new_lines).rstrip()
            return f"{base}\n\n{panel_start}\n{report_text.strip()}\n{panel_end}\n"
        _, row_end = _collect_table_rows(new_lines, header_idx2 + 1)

    insertion = [panel_start, report_text.strip(), panel_end]
    # Ensure a blank line before the panel for readability.
    if row_end < len(new_lines) and new_lines[row_end].strip() != "":
        insertion = [""] + insertion
    out = new_lines[:row_end] + insertion + new_lines[row_end:]
    return "\n".join(out) + ("\n" if (desc or "").endswith("\n") else "")
