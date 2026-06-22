from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from jinja2 import Template

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with the configured LLM endpoint."""

    _prompt_chars_total: int = 0

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
        self._add_prompt_chars(len(prompt))
        # Log outgoing prompt (preview) at INFO for traceability
        prompt_preview = (prompt[:500] + "…") if len(prompt) > 500 else prompt
        prompt_tail = ("…" + prompt[-200:]) if len(prompt) > 700 else ""
        request_meta = self._request_log_meta()
        logger.info(
            "LLM request: endpoint=%s, model=%s, token_param=%s, token_limit=%s, temperature=%s, reasoning_effort=%s, prompt_chars=%d",
            self._endpoint,
            self._model,
            request_meta["token_param"],
            request_meta["token_limit"],
            request_meta["temperature"],
            request_meta["reasoning_effort"],
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

    def generate_with_template(self, issue_payload: Dict[str, Any], template_path: Path, *, system_prompt: Optional[str] = None) -> str:
        template_text = template_path.read_text(encoding="utf-8")
        template = Template(template_text)
        context: Dict[str, Any] = dict(issue_payload or {})
        # Common defaults for templates used across the project
        context.setdefault("title", "")
        context.setdefault("description", "")
        context.setdefault("comments", [])
        context.setdefault("issue_type", "")
        context.setdefault("draft", "")
        context.setdefault("glossary", "")
        prompt = template.render(**context)
        self._add_prompt_chars(len(prompt))
        prompt_preview = (prompt[:500] + "…") if len(prompt) > 500 else prompt
        prompt_tail = ("…" + prompt[-200:]) if len(prompt) > 700 else ""
        request_meta = self._request_log_meta()
        logger.info(
            "LLM request (custom template): endpoint=%s, model=%s, token_param=%s, token_limit=%s, temperature=%s, reasoning_effort=%s, prompt_chars=%d",
            self._endpoint,
            self._model,
            request_meta["token_param"],
            request_meta["token_limit"],
            request_meta["temperature"],
            request_meta["reasoning_effort"],
            len(prompt),
        )
        logger.debug("Prompt preview: %s", prompt_preview)
        if prompt_tail:
            logger.debug("Prompt tail: %s", prompt_tail)

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
            }
            if self._should_send_temperature():
                payload["temperature"] = self._temperature
            reasoning_effort = self._chat_reasoning_effort()
            if reasoning_effort:
                payload["reasoning_effort"] = reasoning_effort
            if self._max_tokens is not None:
                token_key = self._chat_token_param_name()
                payload[token_key] = self._max_tokens
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

    def _chat_token_param_name(self) -> str:
        """Use provider/model-specific token parameter names for chat completions."""
        endpoint = (self._endpoint or "").lower()
        model = (self._model or "").lower()

        # OpenAI GPT-5 chat models use max_completion_tokens instead of max_tokens.
        if "api.openai.com" in endpoint and model.startswith("gpt-5"):
            return "max_completion_tokens"

        return "max_tokens"

    def _should_send_temperature(self) -> bool:
        """Avoid unsupported temperature overrides for OpenAI GPT-5 chat models."""
        endpoint = (self._endpoint or "").lower()
        model = (self._model or "").lower()

        if "api.openai.com" in endpoint and model.startswith("gpt-5"):
            return False

        return True

    def _chat_reasoning_effort(self) -> Optional[str]:
        """Tune reasoning effort for GPT-5 family using currently supported OpenAI values."""
        endpoint = (self._endpoint or "").lower()
        model = (self._model or "").lower()

        if "api.openai.com" in endpoint and model.startswith("gpt-5"):
            # OpenAI GPT-5 chat models accept: none, low, medium, high, xhigh.
            # For release-note summarization we want to avoid spending the budget on hidden reasoning.
            if "nano" in model:
                return "none"
            return "low"

        return None

    def _request_log_meta(self) -> Dict[str, Any]:
        if "/chat/completions" not in (self._endpoint or ""):
            return {
                "token_param": "max_tokens",
                "token_limit": self._max_tokens,
                "temperature": self._temperature,
                "reasoning_effort": "none",
            }

        return {
            "token_param": self._chat_token_param_name(),
            "token_limit": self._max_tokens,
            "temperature": self._temperature if self._should_send_temperature() else "default",
            "reasoning_effort": self._chat_reasoning_effort() or "none",
        }

    @staticmethod
    def _extract_text(response_payload: Dict[str, Any]) -> str:
        """Extract the text output from common LLM response shapes."""
        if "text" in response_payload:
            return response_payload["text"]

        if "output_text" in response_payload:
            output_text = response_payload.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return output_text.strip()

        if "output" in response_payload:
            output_text = LLMClient._extract_text_from_output_items(response_payload["output"])
            if output_text:
                return output_text

        if "result" in response_payload:
            return response_payload["result"]

        choices = response_payload.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                if "text" in choice:
                    return choice["text"]
                message = choice.get("message")
                if isinstance(message, dict):
                    content = LLMClient._extract_message_text(message)
                    if content:
                        return content
                    # DeepSeek sometimes returns the answer only in reasoning_content
                    reasoning = message.get("reasoning_content") or ""
                    trimmed = LLMClient._reasoning_to_text(reasoning)
                    if trimmed:
                        return trimmed

        try:
            payload_preview = json.dumps(response_payload, ensure_ascii=False)[:4000]
        except Exception:
            payload_preview = str(response_payload)[:4000]
        logger.error(
            "Unexpected LLM response format. Top-level keys=%s payload_preview=%s",
            list(response_payload.keys()) if isinstance(response_payload, dict) else type(response_payload).__name__,
            payload_preview,
        )
        raise ValueError("Unexpected LLM response format")

    @staticmethod
    def _extract_message_text(message: Dict[str, Any]) -> str:
        """Handle string and content-part variants used by chat completion APIs."""
        direct_content = message.get("content")
        text = LLMClient._extract_text_from_content_value(direct_content)
        if text:
            return text

        content_parts = message.get("content_parts")
        text = LLMClient._extract_text_from_content_value(content_parts)
        if text:
            return text

        refusal = message.get("refusal")
        text = LLMClient._extract_text_from_content_value(refusal)
        if text:
            return text

        return ""

    @staticmethod
    def _extract_text_from_content_value(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()

        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    stripped = item.strip()
                    if stripped:
                        parts.append(stripped)
                    continue

                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")
                if item_type == "text":
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
                        continue
                    if isinstance(text_value, dict):
                        nested = text_value.get("value")
                        if isinstance(nested, str) and nested.strip():
                            parts.append(nested.strip())
                            continue

                if item_type == "output_text":
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
                        continue

                if item_type == "refusal":
                    refusal_value = item.get("refusal")
                    if isinstance(refusal_value, str) and refusal_value.strip():
                        parts.append(refusal_value.strip())
                        continue

                for key in ("text", "content", "value"):
                    nested_value = item.get(key)
                    if isinstance(nested_value, str) and nested_value.strip():
                        parts.append(nested_value.strip())
                        break
                    if isinstance(nested_value, dict):
                        nested_text = nested_value.get("value")
                        if isinstance(nested_text, str) and nested_text.strip():
                            parts.append(nested_text.strip())
                            break

            return "\n".join(parts).strip()

        if isinstance(value, dict):
            for key in ("text", "content", "value", "refusal"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()

        return ""

    @staticmethod
    def _extract_text_from_output_items(output: Any) -> str:
        if not isinstance(output, list):
            return ""

        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            if item_type == "message":
                text = LLMClient._extract_message_text(item)
                if text:
                    parts.append(text)
                continue

            content = item.get("content")
            text = LLMClient._extract_text_from_content_value(content)
            if text:
                parts.append(text)
                continue

            for key in ("text", "content", "value"):
                nested = item.get(key)
                text = LLMClient._extract_text_from_content_value(nested)
                if text:
                    parts.append(text)
                    break

        return "\n".join(parts).strip()

    @staticmethod
    def _reasoning_to_text(reasoning: str) -> str:
        """Reduce verbose reasoning_content to a single-line answer."""
        if not reasoning:
            return ""
        lowered = reasoning.lower()
        markers = ["ответ:", "final answer:", "result:", "результат:"]
        segment = reasoning
        for m in markers:
            pos = lowered.find(m)
            if pos != -1:
                segment = reasoning[pos + len(m):]
                break
        lines = [ln.strip() for ln in segment.splitlines() if ln.strip()]
        # Heuristics to drop analysis lines and pick the final meaningful one
        def is_noise(line: str) -> bool:
            l = line.lower()
            return l.startswith(("-", "*", "—", "1)", "2)", "3)")) or any(
                kw in l for kw in ["правило", "формат", "эмодзи", "проверяю", "проверка", "сначала анализирую", "тип задачи", "пользовательская ценность"]
            )

        meaningful = [ln for ln in lines if not is_noise(ln)]
        if meaningful:
            return meaningful[-1]
        if lines:
            return lines[-1]
        return segment.strip()

    @classmethod
    def _add_prompt_chars(cls, count: int) -> None:
        try:
            cls._prompt_chars_total += int(count)
        except Exception:
            pass

    @classmethod
    def get_total_prompt_chars(cls) -> int:
        return cls._prompt_chars_total
