# Provider-Specific Patterns

Reference for provider-specific pydantic-ai behavior. Load this when the task involves Bedrock, OpenAI-specific error handling, or model settings that differ per provider. Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- Provider-specific model settings (Bedrock example)
- Provider error mapping tests (`ModelHTTPError`, `ModelAPIError`)

## Provider-specific model settings

Keep default model settings provider-agnostic. Add provider-specific branches only when the provider genuinely needs extra flags:

```python
from pydantic_ai import ModelSettings
from pydantic_ai.models import Model
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelSettings


def _get_model_settings(model: Model) -> ModelSettings:
    settings = ModelSettings(max_tokens=2048, thinking='low')
    if isinstance(model, BedrockConverseModel):
        return BedrockModelSettings(**settings, bedrock_cache_instructions=True)
    return settings
```

Pattern: always build the base `ModelSettings` first, then conditionally upgrade to a provider-specific settings class. This keeps the fallback explicit.

## Provider error mapping tests

pydantic-ai normalizes provider failures before they reach your code: an HTTP error becomes `ModelHTTPError` (`status_code`, `model_name`, `body`), anything else its base class `ModelAPIError` — so `openai.RateLimitError` or Bedrock's `ClientError` never reach an exception handler (Bedrock wraps only `ClientError`; a `botocore.exceptions.BotoCoreError` such as a read timeout propagates unwrapped and needs its own handler). Test that the normalized exceptions map to the correct HTTP status codes. The pattern uses `build_raising_model()` from `references/testing.md`:

```python
from httpx2 import AsyncClient
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError


class TestCatalogAssistantProviderErrors:
    async def test_rate_limit_maps_to_429(self, client: AsyncClient, test_catalog_assistant_agent: Agent) -> None:
        exc = ModelHTTPError(status_code=429, model_name='test')
        with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
            response = await client.post(
                '/v1/assistants/conversations',
                json={'model': 'primary', 'question': 'How many matching items do we have?'},
            )
        assert response.status_code == 429

    async def test_connection_error_maps_to_503(self, client: AsyncClient, test_catalog_assistant_agent: Agent) -> None:
        exc = ModelAPIError(model_name='test', message='Connection error.')
        with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
            response = await client.post(
                '/v1/assistants/conversations',
                json={'model': 'primary', 'question': 'How many matching items do we have?'},
            )
        assert response.status_code == 503
```

## Gotchas

- Provider-specific model settings (e.g., `BedrockModelSettings`) go in one `isinstance` branch per provider in the settings builder; keep each branch narrow.
- Error mapping tests exercise your app's exception handlers, not pydantic-ai. If a test fails, the bug is usually in `app/core/exception_handlers.py`, not in the agent.
- `BedrockConverseModel` lives under `pydantic_ai.models.bedrock` and requires the `bedrock` extra (`pydantic-ai-slim[bedrock]`). Document the extra in `pyproject.toml`.
