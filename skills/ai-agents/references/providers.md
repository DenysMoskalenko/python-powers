# Providers and the Model Registry

Provider wiring for pydantic-ai agents: the clients, the registry that maps an application model name onto a constructed `Model`, provider-specific settings, failover, and turning provider errors into HTTP responses. Load this when adding a provider, tuning model settings, or mapping model failures. The agent itself is in `SKILL.md`; examples use `app/` as the top-level package.

## Contents

- Provider clients
- The registry
- Provider-specific settings belong on the model
- Failover with `FallbackModel`
- Mapping provider errors to HTTP
- Gotchas

## Provider clients

One module per provider under `app/infrastructure/llms/`, each ending in a pydantic-ai `Provider`. The client is `lru_cache`d so its connection pool is built once and shared by every request.

`provider_openai.py`:

```python
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import get_settings, Settings


@lru_cache
def get_openai_client(settings: Annotated[Settings, Depends(get_settings)]) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
        timeout=settings.OPENAI_TIMEOUT,
        base_url=settings.OPENAI_BASE_URL or None,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )


def get_openai_provider(openai_client: Annotated[AsyncOpenAI, Depends(get_openai_client)]) -> OpenAIProvider:
    return OpenAIProvider(openai_client=openai_client)
```

`provider_bedrock.py`, with the same shape:

```python
from functools import lru_cache
from typing import Annotated

import boto3
from botocore.config import Config
from fastapi import Depends
from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
from pydantic_ai.providers.bedrock import BedrockProvider

from app.core.config import get_settings, Settings


@lru_cache
def get_bedrock_client(settings: Annotated[Settings, Depends(get_settings)]) -> BedrockRuntimeClient:
    return boto3.client(
        'bedrock-runtime',
        region_name=settings.AWS_REGION,
        config=Config(
            connect_timeout=settings.BEDROCK_CONNECT_TIMEOUT,
            read_timeout=settings.BEDROCK_READ_TIMEOUT,
            max_pool_connections=settings.BEDROCK_CONNECTIONS_POOL_SIZE,
        ),
    )


def get_bedrock_provider(
    bedrock_client: Annotated[BedrockRuntimeClient, Depends(get_bedrock_client)],
) -> BedrockProvider:
    return BedrockProvider(bedrock_client=bedrock_client)
```

boto3 resolves credentials from the ambient chain; read them from `Settings` and pass them explicitly only where the deployment has no role to assume. Pin the SDK's own retry policy explicitly on both clients (`max_retries` on the OpenAI client, `Config(retries={'max_attempts': ..., 'mode': 'standard'})` on boto3): that loop is separate from the agent's `retries` budget, which never covers transport errors.

## The registry

```python
from typing import Annotated

from fastapi import Depends
from pydantic_ai.models import Model
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelSettings
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import get_settings, Settings
from app.core.enums import AssistantModelName
from app.infrastructure.llms.provider_bedrock import get_bedrock_provider
from app.infrastructure.llms.provider_openai import get_openai_provider

type ModelRegistry = dict[AssistantModelName, Model]


def get_default_model(
    settings: Annotated[Settings, Depends(get_settings)],
    openai_provider: Annotated[OpenAIProvider, Depends(get_openai_provider)],
) -> Model:
    return OpenAIResponsesModel(
        model_name=settings.ASSISTANT_DEFAULT_MODEL_ID,
        provider=openai_provider,
        settings=OpenAIResponsesModelSettings(openai_prompt_cache_key=settings.ASSISTANT_PROMPT_CACHE_KEY),
    )


def get_fast_model(
    settings: Annotated[Settings, Depends(get_settings)],
    bedrock_provider: Annotated[BedrockProvider, Depends(get_bedrock_provider)],
) -> Model:
    return BedrockConverseModel(
        model_name=settings.ASSISTANT_FAST_MODEL_ID,
        provider=bedrock_provider,
        settings=BedrockModelSettings(bedrock_cache_instructions=True, bedrock_cache_tool_definitions=True),
    )


def get_model_registry(
    default_model: Annotated[Model, Depends(get_default_model)],
    fast_model: Annotated[Model, Depends(get_fast_model)],
) -> ModelRegistry:
    return {
        AssistantModelName.DEFAULT: FallbackModel(default_model, fast_model),
        AssistantModelName.FAST: fast_model,
    }
```

`ModelRegistry` is what the agent dependency in `SKILL.md` indexes with `payload.model`.

A second agent that needs its own model-level settings — a different prompt cache key, a different reasoning budget — gets its own registry dependency, not a new `AssistantModelName` member. The enum stays the caller-facing vocabulary, and the extra registry reuses whichever model dependencies it can:

```python
def get_support_default_model(
    settings: Annotated[Settings, Depends(get_settings)],
    openai_provider: Annotated[OpenAIProvider, Depends(get_openai_provider)],
) -> Model:
    return OpenAIResponsesModel(
        model_name=settings.ASSISTANT_DEFAULT_MODEL_ID,
        provider=openai_provider,
        settings=OpenAIResponsesModelSettings(openai_prompt_cache_key=settings.SUPPORT_PROMPT_CACHE_KEY),
    )


def get_support_model_registry(
    support_default_model: Annotated[Model, Depends(get_support_default_model)],
    fast_model: Annotated[Model, Depends(get_fast_model)],
) -> ModelRegistry:
    return {
        AssistantModelName.DEFAULT: FallbackModel(support_default_model, fast_model),
        AssistantModelName.FAST: fast_model,
    }
```

Each agent dependency in `SKILL.md` then depends on its own registry.

## Provider-specific settings belong on the model

Pass them to the `Model` constructor as `settings=` — Bedrock's cache flags, the Responses API's prompt cache key — so the agent builder stays provider-agnostic and never grows an `isinstance` branch. `Model.prepare_request` merges the model's own settings as the base underneath the agent- and run-level ones, so a model contributes what only it understands while the agent's `max_tokens` still wins a collision.

`OpenAIResponsesModel` is the class for the Responses API, where reasoning-item continuity and the built-in tools live. `OpenAIChatModel` targets Chat Completions: it takes the same `openai_prompt_cache_key` but carries none of that continuity.

## Failover with `FallbackModel`

`FallbackModel(primary, secondary)` tries each model in order and moves on when one raises a `ModelAPIError`, which `ModelHTTPError` subclasses; when every model fails it raises `FallbackExceptionGroup`. That is automatic failover inside one request, a different thing from the caller-facing `AssistantModelName.FAST`, which is a model the caller deliberately asked for.

## Mapping provider errors to HTTP

pydantic-ai normalizes provider failures before they leave the model class: an HTTP status becomes `ModelHTTPError`, anything else becomes `ModelAPIError`. Application code never sees `openai.RateLimitError` or `botocore.exceptions.ClientError`, so a handler registered for one of those never fires.

Four handlers in `app/core/exception_handlers.py`, in the return form `fastapi-service` uses:

```python
from fastapi import HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, ModelHTTPError, UsageLimitExceeded
from starlette import status

PROVIDER_RATE_LIMIT_DETAIL = 'Too many requests to the AI provider. Please try again in a moment.'
PROVIDER_BAD_GATEWAY_DETAIL = 'The AI provider rejected the request. Please try again later.'
PROVIDER_UNAVAILABLE_DETAIL = 'AI provider temporarily unavailable. Please retry shortly.'
USAGE_LIMIT_DETAIL = 'The assistant exceeded its per-request budget. Please retry with a narrower question.'


async def model_http_error_handler(request: Request, exc: ModelHTTPError) -> Response:
    if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        rate_limited = HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=PROVIDER_RATE_LIMIT_DETAIL)
        return await http_exception_handler(request, rate_limited)
    rejected = HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PROVIDER_BAD_GATEWAY_DETAIL)
    return await http_exception_handler(request, rejected)


async def model_api_error_handler(request: Request, exc: ModelAPIError) -> Response:  # noqa: ARG001
    unavailable = HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PROVIDER_UNAVAILABLE_DETAIL)
    return await http_exception_handler(request, unavailable)


async def fallback_exception_group_handler(request: Request, exc: FallbackExceptionGroup) -> Response:  # noqa: ARG001
    unavailable = HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PROVIDER_UNAVAILABLE_DETAIL)
    return await http_exception_handler(request, unavailable)


async def usage_limit_exceeded_handler(request: Request, exc: UsageLimitExceeded) -> Response:  # noqa: ARG001
    over_budget = HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=USAGE_LIMIT_DETAIL)
    return await http_exception_handler(request, over_budget)


EXCEPTION_HANDLERS: ExceptionHandlers = {
    ModelHTTPError: model_http_error_handler,
    ModelAPIError: model_api_error_handler,
    FallbackExceptionGroup: fallback_exception_group_handler,
    UsageLimitExceeded: usage_limit_exceeded_handler,
}
```

`EXCEPTION_HANDLERS` and its `ExceptionHandlers` alias belong to `fastapi-service`, which declares the dictionary in this same module and hands it to `FastAPI(exception_handlers=...)`. Add these entries to that literal; assign into it (`EXCEPTION_HANDLERS[ModelHTTPError] = ...`) when it is built elsewhere, and never rebind the name, which drops the domain handlers already registered there.

Register all four. Starlette resolves a handler by walking the exception's MRO and taking the first match it finds in the mapping, so `ModelHTTPError` reaches its own handler and every other model failure falls through to `ModelAPIError`. A rate limit stays a rate limit; anything else the provider rejected is a 502 because the upstream call failed, not the client's request. The last two entries are not reachable through `ModelAPIError`: `FallbackExceptionGroup` is an `ExceptionGroup`, so a `FallbackModel` in the registry whose members all fail 500s without its own entry, and `UsageLimitExceeded` is an agent error raised before any provider is called.

One parametrized test covers the whole mapping, driving the endpoint through a model that raises. `build_raising_model` and the `test_catalog_assistant_agent` fixture come from `references/testing.md`:

```python
from httpx2 import AsyncClient
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
import pytest

from app.domains.catalog_assistant.schemas import CatalogAssistantDeps, CatalogAssistantResponse


@pytest.mark.parametrize(('status_code', 'expected_status'), [(429, 429), (400, 502), (500, 502)])
async def test_model_http_error_maps_by_status_code(
    client: AsyncClient,
    test_catalog_assistant_agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse],
    status_code: int,
    expected_status: int,
) -> None:
    exc = ModelHTTPError(status_code=status_code, model_name='test')
    with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
        response = await client.post(
            '/v1/assistants/conversations', json={'model': 'default', 'question': 'How many hardware items?'}
        )

    assert response.status_code == expected_status
```

To prove the normalization itself rather than trust it, build a real `AsyncOpenAI` client on an `httpx2.MockTransport` that answers 429, wrap it in a real `OpenAIResponsesModel`, and assert the endpoint returns 429. That test needs `override_allow_model_requests(True)` around the call, since the session blocks model requests.

## Gotchas

- `pydantic-ai-slim` ships no provider SDKs. Install the extras you use, as in `pydantic-ai-slim[openai,bedrock]`, and record them in `pyproject.toml`.
- The registry functions return `Model`, so `model.settings` is the base `ModelSettings` TypedDict and a test that indexes a provider key (`model.settings['openai_prompt_cache_key']`) fails the type check with `Unknown key`. Read it through `dict(model.settings or {})`, or narrow the return annotation to the concrete model class in the one place a test needs the provider key.
- The OpenAI SDK depends on `httpx2`, not `httpx`. Test doubles import `AsyncClient`, `MockTransport`, `Request` and `Response` from `httpx2`, and importing them from `httpx` fails the type check because the package is not installed.
