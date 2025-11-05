from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from jinja2 import Template

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with the configured LLM endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        template_path: Path,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = 256,
        timeout: int = 30,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._template_path = template_path

    def generate_summary(self, issue_payload: Dict[str, Any]) -> str:
        prompt = self._render_prompt(issue_payload)
        # Log outgoing prompt (preview) at INFO for traceability
        prompt_preview = (prompt[:500] + "…") if len(prompt) > 500 else prompt
        prompt_tail = ("…" + prompt[-200:]) if len(prompt) > 700 else ""
        logger.info(
            "Sending prompt to LLM: endpoint=%s, model=%s, temperature=%s, max_tokens=%s, prompt_chars=%d",
            self._endpoint,
            self._model,
            self._temperature,
            self._max_tokens,
            len(prompt),
        )
        logger.debug("Prompt preview: %s", prompt_preview)
        if prompt_tail:
            logger.debug("Prompt tail: %s", prompt_tail)

        response = self._invoke_llm(prompt, system_prompt=None)
        summary = self._extract_text(response)

        # Log received summary (preview)
        summary_preview = (summary[:500] + "…") if len(summary) > 500 else summary
        summary_tail = ("…" + summary[-200:]) if len(summary) > 700 else ""
        logger.info("Received LLM response: summary_chars=%d", len(summary))
        logger.debug("Summary preview: %s", summary_preview)
        if summary_tail:
            logger.debug("Summary tail: %s", summary_tail)
        return summary.strip()

    def generate_with_template(self, issue_payload: Dict[str, Any], template_path: Path) -> str:
        template_text = template_path.read_text(encoding="utf-8")
        template = Template(template_text)
        prompt = template.render(
            title=issue_payload.get("title", ""),
            description=issue_payload.get("description", ""),
            comments=issue_payload.get("comments", []),
            issue_type=issue_payload.get("issue_type", ""),
        )
        prompt_preview = (prompt[:500] + "…") if len(prompt) > 500 else prompt
        prompt_tail = ("…" + prompt[-200:]) if len(prompt) > 700 else ""
        logger.info(
            "Sending prompt to LLM (custom template): endpoint=%s, model=%s, temperature=%s, max_tokens=%s, prompt_chars=%d",
            self._endpoint,
            self._model,
            self._temperature,
            self._max_tokens,
            len(prompt),
        )
        logger.debug("Prompt preview: %s", prompt_preview)
        if prompt_tail:
            logger.debug("Prompt tail: %s", prompt_tail)

        # Provide a focused system prompt for short summaries
        system_prompt = (
            "Вы — технический редактор релиз-нот. Пиши кратко на русском. "
            "Если задача сугубо техническая — верни ровно: не описываем."
        )
        response = self._invoke_llm(prompt, system_prompt=system_prompt)
        summary = self._extract_text(response)
        summary_preview = (summary[:500] + "…") if len(summary) > 500 else summary
        summary_tail = ("…" + summary[-200:]) if len(summary) > 700 else ""
        logger.info("Received LLM response: summary_chars=%d", len(summary))
        logger.debug("Summary preview: %s", summary_preview)
        if summary_tail:
            logger.debug("Summary tail: %s", summary_tail)
        return summary.strip()

    def _render_prompt(self, issue_payload: Dict[str, Any]) -> str:
        template_text = self._template_path.read_text(encoding="utf-8")
        template = Template(template_text)
        prompt = template.render(
            title=issue_payload.get("title", ""),
            description=issue_payload.get("description", ""),
            comments=issue_payload.get("comments", []),
        )
        logger.debug("Rendered prompt length: %s characters", len(prompt))
        return prompt

    def _invoke_llm(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Choose OpenAI-compatible payload shape based on endpoint path
        is_chat = "/chat/completions" in self._endpoint

        if is_chat:
            if not self._model:
                raise ValueError(
                    "LLM_MODEL is required for /v1/chat/completions endpoints"
                )
            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "temperature": self._temperature,
            }
            if self._max_tokens is not None:
                payload["max_tokens"] = self._max_tokens
        else:
            payload = {
                "prompt": prompt,
                "temperature": self._temperature,
            }
            if self._model:
                payload["model"] = self._model
            if self._max_tokens is not None:
                payload["max_tokens"] = self._max_tokens

        logger.debug("Sending request to LLM endpoint %s", self._endpoint)
        response = requests.post(
            self._endpoint,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            # Include response body (if any) to aid debugging
            try:
                err_text = response.text
            except Exception:
                err_text = "<no response body>"
            logger.error("LLM endpoint returned an error: %s\nBody: %s", exc, err_text)
            raise

        # Log raw response preview at DEBUG level
        try:
            body_preview = response.text[:800]
            logger.debug("LLM raw response preview: %s", body_preview)
        except Exception:
            pass

        return response.json()

    @staticmethod
    def _extract_text(response_payload: Dict[str, Any]) -> str:
        """Extract the text output from common LLM response shapes."""
        if "text" in response_payload:
            return response_payload["text"]

        if "output" in response_payload:
            return response_payload["output"]

        if "result" in response_payload:
            return response_payload["result"]

        choices = response_payload.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                if "text" in choice:
                    return choice["text"]
                message = choice.get("message")
                if isinstance(message, dict) and "content" in message:
                    return message["content"]

        raise ValueError("Unexpected LLM response format")
