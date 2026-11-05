import httpx
import pytest

from aivora.config import Settings
from aivora.db import Organization
from aivora.providers import ProviderUnavailable, generate

SOURCE = [{"text": "Annual leave is 21 days.", "title": "Policy"}]


@pytest.mark.parametrize("provider", ["groq", "gemini"])
def test_provider_contract_and_usage(provider, monkeypatch):
    settings = Settings(
        provider=provider,
        model="test-model",
        groq_key="test-secret",
        google_key="test-secret",
    )
    original_client = httpx.Client

    def handler(request):
        assert "test-secret" not in str(request.url)
        assert request.url.host in {"api.groq.com", "generativelanguage.googleapis.com"}
        if provider == "groq":
            assert request.headers["Authorization"] == "Bearer test-secret"
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "Annual leave is 21 days [1]."}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10},
                },
            )
        assert request.headers["x-goog-api-key"] == "test-secret"
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Annual leave is 21 days [1]."}]}}],
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 10},
            },
        )

    monkeypatch.setattr(
        "aivora.providers.httpx.Client",
        lambda **kw: original_client(transport=httpx.MockTransport(handler)),
    )
    result = generate(
        settings,
        Organization(assistant_name="Guide", guidance="Be concise"),
        "Annual leave?",
        SOURCE,
    )
    assert result.input_tokens == 50 and result.output_tokens == 10
    assert "21 days" in result.text


def test_invalid_citation_rejected(monkeypatch):
    original_client = httpx.Client
    monkeypatch.setattr(
        "aivora.providers.httpx.Client",
        lambda **kw: original_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "Unsupported claim [999]."}}]},
                )
            )
        ),
    )
    answer = generate(
        Settings(provider="groq", model="test", groq_key="test"),
        Organization(assistant_name="Guide", guidance="Be concise"),
        "Leave?",
        SOURCE,
    )
    assert "citation validation" in answer.text and "Unsupported claim" not in answer.text


def test_provider_error_does_not_expose_response(monkeypatch):
    original_client = httpx.Client
    monkeypatch.setattr(
        "aivora.providers.httpx.Client",
        lambda **kw: original_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(401, text="private-provider-secret")
            )
        ),
    )
    with pytest.raises(ProviderUnavailable) as error:
        generate(
            Settings(provider="groq", model="test", groq_key="test"),
            Organization(assistant_name="Guide", guidance="Be concise"),
            "Leave?",
            SOURCE,
        )
    assert "private-provider-secret" not in str(error.value)
