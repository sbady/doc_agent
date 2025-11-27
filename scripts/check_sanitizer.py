from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jira_client import JiraClient  # type: ignore
from release_notes import sanitize_issue_data  # type: ignore


def compare_fields(raw: Dict[str, Any], sanitized: Dict[str, Any]) -> List[str]:
    changes: List[str] = []
    for key in ("title", "description", "issue_type"):
        if raw.get(key, "") != sanitized.get(key, ""):
            changes.append(
                f"[{key}] RAW:\n{raw.get(key,'')}\n\n[{key}] SANITIZED:\n{sanitized.get(key,'')}\n"
            )

    raw_comments = raw.get("comments", []) or []
    sanitized_comments = sanitized.get("comments", []) or []
    max_len = max(len(raw_comments), len(sanitized_comments))
    for i in range(max_len):
        raw_c = raw_comments[i] if i < len(raw_comments) else ""
        san_c = sanitized_comments[i] if i < len(sanitized_comments) else ""
        if raw_c != san_c:
            changes.append(f"[comment #{i}] RAW:\n{raw_c}\n\n[comment #{i}] SANITIZED:\n{san_c}\n")

    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Check sanitizer output for a Jira issue.")
    parser.add_argument("issue_key", nargs="?", help="Jira issue key (e.g., MSP-1234)")
    args = parser.parse_args()

    load_dotenv()

    issue_key = args.issue_key or os.getenv("JIRA_ISSUE_KEY")
    if not issue_key:
        print("Issue key is required (pass as argument or set JIRA_ISSUE_KEY in .env)")
        return 1

    jira = JiraClient(
        base_url=os.environ["JIRA_BASE_URL"],
        email=os.getenv("JIRA_EMAIL"),
        api_token=os.environ["JIRA_API_TOKEN"],
        auth_type=os.getenv("JIRA_AUTH_TYPE", "pat"),
        api_version=os.getenv("JIRA_API_VERSION", "latest"),
        timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
    )

    try:
        raw_issue = jira.get_issue_data(issue_key)
    except Exception as exc:
        print(f"Failed to fetch issue {issue_key}: {exc}")
        return 1

    sanitized = sanitize_issue_data(raw_issue)
    changes = compare_fields(raw_issue, sanitized)

    if not changes:
        print("No changes after sanitization (raw == sanitized).")
    else:
        print("\n--- Sanitizer differences ---\n")
        for change in changes:
            print(change)
            print("-" * 40)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
