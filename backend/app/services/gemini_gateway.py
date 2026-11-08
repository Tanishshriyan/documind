from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from app.core.config import Settings

try:  # Keep import-time failures clear in environments before dependencies install.
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised by the setup check, not production.
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)
T = TypeVar("T")


class GeminiError(Exception):
    status_code = 502
    public_message = "Gemini could not process the request. Please try again."


class GeminiConfigurationError(GeminiError):
    status_code = 503
    public_message = "Gemini is not configured. Add GEMINI_API_KEY to the backend environment."


class GeminiQuotaError(GeminiError):
    status_code = 429
    public_message = "Gemini is temporarily rate-limited. Please try again in a moment."


class GeminiTransientError(GeminiError):
    status_code = 503
    public_message = "Gemini is temporarily unavailable. Please try again shortly."


class GeminiProviderError(GeminiError):
    status_code = 502


@dataclass
class GeminiGateway:
    settings: Settings | None = None
    client: Any | None = None
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.settings is None:
            from app.core.config import get_settings

            self.settings = get_settings()

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.settings.gemini_api_key:
            raise GeminiConfigurationError()
        if genai is None:
            raise GeminiConfigurationError("The google-genai package is not installed.")
        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(self.settings.gemini_timeout_seconds * 1000)),
        )
        return self.client

    def call(self, operation: str, request: Callable[[Any], T]) -> T:
        attempts = max(0, self.settings.gemini_max_retries) + 1
        for attempt in range(attempts):
            try:
                return request(self._get_client())
            except GeminiError:
                raise
            except Exception as exc:
                kind = classify_gemini_error(exc)
                if kind == "auth":
                    raise GeminiConfigurationError() from exc
                if kind == "quota":
                    if attempt >= attempts - 1:
                        raise GeminiQuotaError() from exc
                elif kind == "transient":
                    if attempt >= attempts - 1:
                        raise GeminiTransientError() from exc
                else:
                    raise GeminiProviderError() from exc

                delay = min(2**attempt, 8)
                logger.warning("Gemini %s request failed (%s); retrying in %ss", operation, kind, delay)
                self.sleep(delay)
        raise GeminiProviderError()

    def embed_content(self, contents: list[str], output_dimension: int) -> Any:
        if types is None:
            raise GeminiConfigurationError("The google-genai package is not installed.")
        return self.call(
            "embedding",
            lambda client: client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=output_dimension),
            ),
        )

    def generate_answer(self, prompt: str, system_instruction: str) -> Any:
        return self.call(
            "generation",
            lambda client: client.interactions.create(
                model=self.settings.gemini_model,
                input=prompt,
                system_instruction=system_instruction,
                store=False,
            ),
        )


def classify_gemini_error(error: Exception) -> str:
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if code is None and response is not None:
        code = getattr(response, "status_code", None)
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None

    message = str(error).lower()
    if code in {401, 403} or any(term in message for term in ("api key", "unauthorized", "permission denied", "authentication")):
        return "auth"
    if code == 429 or any(term in message for term in ("rate limit", "quota", "resource exhausted", "resource_exhausted", "too many requests")):
        return "quota"
    if code in {408, 500, 502, 503, 504} or any(term in message for term in ("timeout", "timed out", "deadline exceeded", "temporarily unavailable", "connection reset")):
        return "transient"
    return "permanent"

