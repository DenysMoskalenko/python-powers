---
name: ai-agents
description: Use when building, integrating, or testing pydantic-ai agents inside a FastAPI service — defining the Agent, typed dependencies, tools, system prompts, model registry, agent-as-FastAPI-dependency wiring, or agent test fixtures (TestModel, FunctionModel, provider error mapping).
---

# AI Agent Patterns

Patterns for building pydantic-ai agents integrated into FastAPI services.

> Requires Python 3.13+, pydantic-ai, FastAPI.
> Examples use `app/` as the top-level package (the reference project's convention). Substitute your package name if different.

**Related**: `python-code-style`, `fastapi-service`, `python-testing`.

For generic FastAPI route/service patterns use `fastapi-service`. For database queries use `postgres-database`. For shared test infrastructure use `python-testing`.

## Agent dependencies

Define agent dependencies as a frozen dataclass. The agent receives these at runtime via `deps`:

```python
from dataclasses import dataclass

from app.services.catalog_service import CatalogService


@dataclass(frozen=True, slots=True)
class CatalogAssistantDeps:
    catalog_service: CatalogService
```

- `frozen=True` — immutable, safe for concurrent use
- `slots=True` — memory efficient
- Include only what the agent's tools need (services, config, session)

## Agent factory

Separate the agent builder from the FastAPI dependency. The builder creates the agent with a given model — this makes testing trivial:

```python
from fastapi_pagination import Params
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.models import Model

from app.agents.catalog_assistant.prompts import CATALOG_ASSISTANT_SYSTEM_PROMPT
from app.agents.catalog_assistant.schemas import (
    CatalogAssistantDeps,
    CatalogToolItem,
    CountCatalogItemsToolInput,
    ListCatalogItemsToolInput,
)
from app.api.catalog.schemas import CatalogListSorting
from app.api.catalog_assistant.schemas import CatalogAssistantResponse


def build_catalog_assistant_agent(model: Model) -> Agent[CatalogAssistantDeps, CatalogAssistantResponse]:
    agent = Agent[CatalogAssistantDeps, CatalogAssistantResponse](
        model=model,
        output_type=CatalogAssistantResponse,
        deps_type=CatalogAssistantDeps,
        system_prompt=CATALOG_ASSISTANT_SYSTEM_PROMPT,
        retries=0,
        model_settings=ModelSettings(max_tokens=2048, thinking='low', temperature=0.7),
    )

    @agent.tool
    async def count_items(ctx: RunContext[CatalogAssistantDeps], payload: CountCatalogItemsToolInput) -> int:
        return await ctx.deps.catalog_service.count_items(payload.filters)

    @agent.tool
    async def list_items(
        ctx: RunContext[CatalogAssistantDeps], payload: ListCatalogItemsToolInput
    ) -> list[CatalogToolItem]:
        items_page = await ctx.deps.catalog_service.list_items(
            payload.filters,
            CatalogListSorting(sort_by='name', sort_order='asc'),
            pagination_params=Params(page=1, size=payload.limit),
        )
        return [CatalogToolItem.model_validate(item, from_attributes=True) for item in items_page.items]

    return agent
```

Key patterns:
- `Agent[Deps, Output]` — fully typed with dependency and output types
- Tools registered with `@agent.tool` inside the builder — each tool gets `RunContext[Deps]`
- Tool inputs are Pydantic `BaseModel` subclasses — the LLM sees their JSON schema
- Tools call services from `ctx.deps`, never import globals
- `retries=0` to fail fast; retries mask real failures in tests and production alike

## Tool input schemas

Tool parameters are Pydantic models. The LLM sees them as function parameter schemas:

```python
from pydantic import BaseModel, Field

from app.api.catalog.schemas import CatalogListFilters


class CountCatalogItemsToolInput(BaseModel):
    filters: CatalogListFilters = Field(default_factory=CatalogListFilters)


class ListCatalogItemsToolInput(BaseModel):
    filters: CatalogListFilters = Field(default_factory=CatalogListFilters)
    limit: int = Field(default=20, ge=1, le=100)
```

## System prompts

Keep system prompts in a separate `prompts.py` module. Write them as rules, not descriptions:

```python
CATALOG_ASSISTANT_SYSTEM_PROMPT = """
You are a read-only assistant for a service catalog API.

Rules:
- Use `count_items` for questions asking "how many", totals, or counts.
- Use `list_items` for questions asking for examples, names, or lists.
- Stay within the catalog domain. If the question is unrelated, refuse politely.
- Be concise and factual.
""".strip()
```

Rules outperform descriptions ("Use X for Y" beats "You can use X").

## Model registry

A `TypeAlias` mapping request model names to fully constructed `Model` instances. Keep provider wiring in `infrastructure/llms/`:

```python
from typing import Annotated, TypeAlias

from fastapi import Depends
from pydantic_ai.models import Model

from app.api.catalog_assistant.schemas import AssistantModelName
from app.infrastructure.llms.registry import get_fallback_model, get_primary_model

ModelRegistry: TypeAlias = dict[AssistantModelName, Model]


def get_model_registry(
    primary_model: Annotated[Model, Depends(get_primary_model)],
    fallback_model: Annotated[Model, Depends(get_fallback_model)],
) -> ModelRegistry:
    return {
        AssistantModelName.PRIMARY: primary_model,
        AssistantModelName.FALLBACK: fallback_model,
    }
```

Use `StrEnum` for model names — serializes cleanly in JSON:

```python
from enum import StrEnum


class AssistantModelName(StrEnum):
    PRIMARY = 'primary'
    FALLBACK = 'fallback'
```

## Agent as FastAPI dependency

The agent dependency reads the request payload to select the model, then builds the agent:

```python
from typing import Annotated

from fastapi import Depends
from pydantic_ai import Agent

from app.agents.catalog_assistant.builder import build_catalog_assistant_agent
from app.agents.catalog_assistant.dependencies import ModelRegistry, get_model_registry
from app.agents.catalog_assistant.schemas import CatalogAssistantDeps
from app.api.catalog_assistant.schemas import CatalogAssistantRequest, CatalogAssistantResponse


def get_catalog_assistant_agent(
    payload: CatalogAssistantRequest,
    model_registry: Annotated[ModelRegistry, Depends(get_model_registry)],
) -> Agent[CatalogAssistantDeps, CatalogAssistantResponse]:
    return build_catalog_assistant_agent(model_registry[payload.model])
```

## Agent service

A thin service that calls `agent.run()` with the assembled deps:

```python
from typing import Annotated

from fastapi import Depends
from pydantic_ai import Agent

from app.agents.catalog_assistant.schemas import CatalogAssistantDeps
from app.api.catalog_assistant.schemas import CatalogAssistantRequest, CatalogAssistantResponse
from app.services.catalog_service import CatalogService


class CatalogAssistantService:
    def __init__(self, catalog_service: Annotated[CatalogService, Depends()]) -> None:
        self._catalog_service = catalog_service

    async def answer(
        self,
        payload: CatalogAssistantRequest,
        agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse],
    ) -> CatalogAssistantResponse:
        result = await agent.run(payload.question, deps=CatalogAssistantDeps(catalog_service=self._catalog_service))
        return result.output
```

## Agent route

The route injects both service and agent, delegates to the service:

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic_ai import Agent

from app.agents.catalog_assistant.dependencies import get_catalog_assistant_agent
from app.agents.catalog_assistant.schemas import CatalogAssistantDeps
from app.api.catalog_assistant.schemas import CatalogAssistantRequest, CatalogAssistantResponse
from app.services.catalog_assistant_service import CatalogAssistantService

router = APIRouter(tags=['Catalog Assistant'])


@router.post('/assistants/conversations')
async def create_response(
    payload: CatalogAssistantRequest,
    service: Annotated[CatalogAssistantService, Depends()],
    agent: Annotated[Agent[CatalogAssistantDeps, CatalogAssistantResponse], Depends(get_catalog_assistant_agent)],
) -> CatalogAssistantResponse:
    return await service.answer(payload, agent)
```

## Testing

See `reference/testing.md` for the full test pattern: blocking real model requests, `TestModel` fixture, `FunctionModel` for deterministic responses, and `agent.override()` for per-test model swaps.

## Provider-specific behavior

See `reference/providers.md` for provider-specific model settings (Bedrock caching) and provider error mapping tests (Bedrock `ClientError`, OpenAI `RateLimitError` → HTTP status mapping).

## Red Flags — STOP

These mean the agent boundary is drifting. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Import a service directly inside an agent tool | Agent dependencies — tools use `ctx.deps` only |
| Write a system prompt as "You can use..." | System prompts — write rules as "Use X for Y" |
| Set `retries > 0` on the agent | Agent factory — use `retries=0` so failures surface |
| Instantiate provider models inside the model registry | Model registry — delegate provider wiring to `infrastructure/llms/` |
| Let tests run without `ALLOW_MODEL_REQUESTS = False` | Testing — block real model requests globally |
| Resolve output tools in mocks by list index | Testing — resolve output tools by schema keys |

## Gotchas

- `ALLOW_MODEL_REQUESTS = False` must be in `pytest_configure` before any agent import
- Agent tools access services through `ctx.deps` only — never import at module level
- `agent.override()` is scoped to a `with` block; original model is restored automatically
- Provider-specific model settings (e.g., `BedrockModelSettings`) require `isinstance` checks
