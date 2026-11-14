from unittest.mock import patch

import pytest

from cthulu_agent.llm import LLMClient, LLMError, LLMManager


ACCOUNT_ID = "0123456789abcdef0123456789abcdef"


def test_cloudflare_provider_defaults_to_low_cost_agentic_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cloudflare")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "test-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.delenv("CLOUDFLARE_BASE_URL", raising=False)

    manager = LLMManager()
    config = manager.provider_config("cloudflare")

    assert manager.configured
    assert config["model"] == "@cf/qwen/qwen3-30b-a3b-fp8"
    assert config["base_url"] == (
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1"
    )


def test_cloudflare_chat_uses_gateway_and_openai_compatible_endpoint():
    client = LLMClient(
        "cloudflare",
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1",
        "test-token",
        "@cf/qwen/qwen3-30b-a3b-fp8",
        account_id=ACCOUNT_ID,
        gateway_id="default",
    )
    response = {
        "model": "@cf/qwen/qwen3-30b-a3b-fp8",
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }

    with patch("cthulu_agent.llm._http", return_value=(200, response, {})) as request:
        result = client.chat([{"role": "user", "content": "Reply OK"}], retries=0)

    args, kwargs = request.call_args
    assert args[0] == "POST"
    assert args[1].endswith("/ai/v1/chat/completions")
    assert args[2]["cf-aig-gateway-id"] == "default"
    assert kwargs == {}
    assert result.text == "OK"


def test_cloudflare_model_discovery_returns_all_catalog_pages(monkeypatch):
    client = LLMClient(
        "cloudflare", "", "test-token", "unused",
        account_id=ACCOUNT_ID, gateway_id="default",
    )
    first_page = [{"id": f"model-{i}", "name": f"Model {i}"} for i in range(100)]
    second_page = [{"id": "model-100", "name": "Model 100"}]
    with patch(
        "cthulu_agent.llm._http",
        side_effect=[
            (200, {"success": True, "result": {"data": first_page}}, {}),
            (200, {"success": True, "result": {"data": second_page}}, {}),
        ],
    ) as request:
        models = client.list_models()

    assert len(models) == 101
    assert {model["id"] for model in models} == {f"model-{i}" for i in range(101)}
    assert request.call_count == 2
    assert "/ai/models/search?" in request.call_args_list[0].args[1]


def test_cloudflare_chat_requires_account_id():
    client = LLMClient("cloudflare", "", "test-token", "model")

    with pytest.raises(LLMError, match="Account ID is required"):
        client.chat([{"role": "user", "content": "hello"}], retries=0)
