from types import SimpleNamespace

import pytest

from app.services.gemini_gateway import GeminiConfigurationError, GeminiGateway, GeminiQuotaError


class ApiError(Exception):
    def __init__(self, code: int):
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeInteractions:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    def create(self, **_: object):
        self.calls += 1
        raise self.error


def test_quota_errors_are_retried_then_exposed():
    interactions = FakeInteractions(ApiError(429))
    client = SimpleNamespace(interactions=interactions)
    settings = SimpleNamespace(gemini_api_key="secret", gemini_model="gemini-3.8-flash", gemini_max_retries=2, gemini_timeout_seconds=1)
    gateway = GeminiGateway(settings=settings, client=client, sleep=lambda _: None)

    with pytest.raises(GeminiQuotaError):
        gateway.generate_answer("question", "grounding")

    assert interactions.calls == 3


def test_auth_errors_are_not_retried():
    interactions = FakeInteractions(ApiError(401))
    client = SimpleNamespace(interactions=interactions)
    settings = SimpleNamespace(gemini_api_key="secret", gemini_model="gemini-3.8-flash", gemini_max_retries=3, gemini_timeout_seconds=1)
    gateway = GeminiGateway(settings=settings, client=client, sleep=lambda _: None)

    with pytest.raises(GeminiConfigurationError):
        gateway.generate_answer("question", "grounding")

    assert interactions.calls == 1


def test_missing_api_key_is_a_configuration_error():
    settings = SimpleNamespace(gemini_api_key=None, gemini_max_retries=3, gemini_timeout_seconds=1)
    gateway = GeminiGateway(settings=settings, sleep=lambda _: None)

    with pytest.raises(GeminiConfigurationError):
        gateway.generate_answer("question", "grounding")

