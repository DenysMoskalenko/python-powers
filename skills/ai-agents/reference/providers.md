# Provider-Specific Patterns

Reference for provider-specific pydantic-ai behavior. Load this when the task involves Bedrock, OpenAI-specific error handling, or model settings that differ per provider. Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- Provider-specific model settings (Bedrock example)
- Provider error mapping tests (Bedrock, OpenAI)

## Provider-specific model settings

Keep default model settings provider-agnostic. Add provider-specific branches only when the provider genuinely needs extra flags:

```python
from pydantic_ai import ModelSettings
from pydantic_ai.models import Model
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelSettings


def _get_model_settings(model: Model) -> ModelSettings:
    settings = ModelSettings(max_tokens=2048, thinking='low', temperature=0.7)
    if isinstance(model, BedrockConverseModel):
        return BedrockModelSettings(**settings, bedrock_cache_instructions=True)
    return settings
```

Pattern: always build the base `ModelSettings` first, then conditionally upgrade to a provider-specific settings class. This keeps the fallback explicit.

## Provider error mapping tests

If the service supports multiple LLM providers, test that provider-specific exceptions map to the correct HTTP status codes. The pattern uses `build_raising_model()` from `reference/testing.md`:

```python
from botocore.exceptions import ClientError
from httpx import AsyncClient, Request, Response
from openai import APIConnectionError, RateLimitError
from pydantic_ai import Agent


class TestCatalogAssistantProviderErrors:
    async def test_bedrock_throttling_maps_to_429(
        self, client: AsyncClient, test_catalog_assistant_agent: Agent
    ) -> None:
        exc = ClientError(
            error_response={'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            operation_name='Converse',
        )
        with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
            response = await client.post(
                '/v1/assistants/conversations',
                json={'model': 'primary', 'question': 'How many matching items do we have?'},
            )
        assert response.status_code == 429

    async def test_openai_rate_limit_maps_to_429(
        self, client: AsyncClient, test_catalog_assistant_agent: Agent
    ) -> None:
        request = Request('POST', 'https://testserver/v1/assistants/conversations')
        exc = RateLimitError('rate limited', response=Response(429, request=request), body={})
        with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
            response = await client.post(
                '/v1/assistants/conversations',
                json={'model': 'primary', 'question': 'How many matching items do we have?'},
            )
        assert response.status_code == 429

    async def test_openai_connection_error_maps_to_503(
        self, client: AsyncClient, test_catalog_assistant_agent: Agent
    ) -> None:
        request = Request('POST', 'https://testserver/v1/assistants/conversations')
        exc = APIConnectionError(message='Connection error.', request=request)
        with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
            response = await client.post(
                '/v1/assistants/conversations',
                json={'model': 'primary', 'question': 'How many matching items do we have?'},
            )
        assert response.status_code == 503
```

## Gotchas

- Provider-specific model settings (e.g., `BedrockModelSettings`) require `isinstance` checks on the model. Keep the check narrow — one `isinstance` per provider branch.
- Error mapping tests exercise your app's exception handlers, not pydantic-ai. If a test fails, the bug is usually in `app/core/exception_handlers.py`, not in the agent.
- `BedrockConverseModel` lives under `pydantic_ai.models.bedrock` and requires the `bedrock` extra (`pydantic-ai-slim[bedrock]`). Document the extra in `pyproject.toml`.
