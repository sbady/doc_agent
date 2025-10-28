from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from environment variables."""

    jira_base_url: str
    jira_api_token: str
    jira_auth_type: str
    jira_api_version: str
    jira_email: Optional[str]
    llm_endpoint: str
    prompt_template_path: Path
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_temperature: float = 0.1
    llm_max_tokens: Optional[int] = 256
    request_timeout: int = 30
    # Release notes extension
    release_parent_key: Optional[str] = None
    target_issue_key: Optional[str] = None
    issue_short_template_path: Path = Path("prompt_templates/issue_short_summary.txt")
    issue_short_max_tokens: Optional[int] = 200

    @staticmethod
    def _load_env() -> None:
        """Load environment variables from a .env file if present."""
        # load_dotenv is idempotent, safe to call multiple times.
        load_dotenv()

    @classmethod
    def load(cls) -> "AppConfig":
        """Create configuration instance from environment variables."""
        cls._load_env()

        jira_base_url = cls._require("JIRA_BASE_URL")
        auth_type = os.getenv("JIRA_AUTH_TYPE", "basic").lower()
        if auth_type not in {"basic", "pat"}:
            raise ValueError("JIRA_AUTH_TYPE must be 'basic' or 'pat'")

        jira_api_token = cls._require("JIRA_API_TOKEN")

        if auth_type == "basic":
            jira_email = cls._require("JIRA_EMAIL")
        else:
            jira_email = os.getenv("JIRA_EMAIL")  # optional for PAT

        llm_endpoint = cls._require("LLM_ENDPOINT")

        jira_api_version = os.getenv("JIRA_API_VERSION", "3").strip() or "3"

        prompt_path_env = os.getenv("PROMPT_TEMPLATE_PATH", "prompt_templates/release_summary.txt")
        prompt_template_path = cls._resolve_path(prompt_path_env)
        if not prompt_template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_template_path}")

        llm_api_key = os.getenv("LLM_API_KEY")
        llm_model = os.getenv("LLM_MODEL")
        llm_temperature = cls._get_float("LLM_TEMPERATURE", default=0.1)
        llm_max_tokens = cls._get_int("LLM_MAX_TOKENS", default=256)
        request_timeout = cls._get_int("REQUEST_TIMEOUT", default=30)

        # Release notes related env
        release_parent_key = os.getenv("RELEASE_PARENT_KEY")
        target_issue_key = os.getenv("TARGET_ISSUE_KEY")
        short_tmpl_env = os.getenv("ISSUE_SHORT_TEMPLATE_PATH", "prompt_templates/issue_short_summary.txt")
        issue_short_template_path = cls._resolve_path(short_tmpl_env)
        issue_short_max_tokens = cls._get_int("ISSUE_SHORT_MAX_TOKENS", default=200)

        return cls(
            jira_base_url=jira_base_url,
            jira_api_token=jira_api_token,
            jira_auth_type=auth_type,
            jira_api_version=jira_api_version,
            jira_email=jira_email,
            llm_endpoint=llm_endpoint,
            prompt_template_path=prompt_template_path,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            llm_max_tokens=llm_max_tokens,
            request_timeout=request_timeout,
            release_parent_key=release_parent_key,
            target_issue_key=target_issue_key,
            issue_short_template_path=issue_short_template_path,
            issue_short_max_tokens=issue_short_max_tokens,
        )

    @classmethod
    def _resolve_path(cls, path_value: str) -> Path:
        path = Path(path_value)
        if not path.is_absolute():
            base_dir = Path(__file__).resolve().parent
            path = base_dir / path
        return path

    @staticmethod
    def _require(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Environment variable {key} is required")
        return value

    @staticmethod
    def _get_int(key: str, default: Optional[int] = None) -> Optional[int]:
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Environment variable {key} must be an integer") from exc

    @staticmethod
    def _get_float(key: str, default: float) -> float:
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"Environment variable {key} must be a float") from exc
