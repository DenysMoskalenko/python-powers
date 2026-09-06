---
name: ai-agents
description: Use when adding an LLM, assistant, or chatbot endpoint to a FastAPI service, or when building or testing pydantic-ai agents — the Agent, instructions, typed deps, tools, model registry with FallbackModel, streaming and message history, ModelHTTPError mapping, and agent test fixtures (TestModel, FunctionModel). pydantic-ai only; in a project already on another framework, follow that framework.
---

# AI Agent Patterns

Patterns for pydantic-ai agents that run inside a FastAPI request. An agent is one feature slice like any other: builder, tools, instructions, service, route and schemas live together under `app/domains/<feature>/`, and only the internals are agent-specific. Model and provider wiring stays in `app/infrastructure/llms/`. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires Python 3.13+, pydantic-ai 2.x (pydantic-ai-slim with the provider extras you use), FastAPI.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `fastapi-service`, `python-testing`, `project-scaffolding`.

## Domain layout

The example is a `catalog_assistant` domain whose tools answer from a sibling `catalog` domain's `CatalogService`.

```text
app/domains/catalog_assistant/
  routes.py            # thin handler; injects the agent
  service.py           # runs the agent with assembled deps and usage limits
  agents.py            # build_*_agent (builder) + get_*_agent (FastAPI dependency)
  prompts.py           # instructions text
  schemas/
    __init__.py        # facade re-exporting both files
    schemas_api.py     # request/response — the HTTP contract, and the agent's output_type
    schemas_agent.py   # agent deps + tool input/output models
app/core/enums.py      # AssistantModelName — the model names a caller may ask for
app/infrastructure/llms/
  registry.py          # model name → constructed Model
  provider_openai.py, provider_bedrock.py   # provider clients and providers
```

The model-name enum lives in `app/core/enums.py`, not in the domain, so `app/infrastructure/llms/registry.py` never imports from `app/domains/`.

## Agent dependencies

Tools reach their collaborators through `ctx.deps`, so the deps object is the agent's whole injection surface — services, config, a session, nothing else.

```python
from dataclasses import dataclass

from app.domains.catalog.service import CatalogService


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogAssistantDeps:
    catalog_service: CatalogService
```

## Building the agent

The builder takes an already-constructed `Model`, so a test hands it `TestModel()` and the same code path runs. Register tools inside the builder with `@agent.tool`.

```python
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.models import Model

from app.domains.catalog.schemas import CatalogListFilters
from app.domains.catalog_assistant.prompts import CATALOG_ASSISTANT_INSTRUCTIONS
from app.domains.catalog_assistant.schemas import (
    CatalogAssistantDeps,
    CatalogAssistantResponse,
    CatalogToolItem,
    ListCatalogItemsToolInput,
)

CATALOG_ASSISTANT_MODEL_SETTINGS = ModelSettings(max_tokens=2048, thinking='low')


def build_catalog_assistant_agent(model: Model) -> Agent[CatalogAssistantDeps, CatalogAssistantResponse]:
    agent = Agent[CatalogAssistantDeps, CatalogAssistantResponse](
        model=model,
        output_type=CatalogAssistantResponse,
        deps_type=CatalogAssistantDeps,
        instructions=CATALOG_ASSISTANT_INSTRUCTIONS,
        model_settings=CATALOG_ASSISTANT_MODEL_SETTINGS,
    )

    @agent.tool
    async def count_items(
        ctx: RunContext[CatalogAssistantDeps], category: str | None = None, name_contains: str | None = None
    ) -> int:
        """Count catalog items matching the given filters.

        Args:
            category: Restrict the count to one catalog category, for example `hardware`.
            name_contains: Restrict the count to items whose name contains this case-insensitive text.
        """
        filters = CatalogListFilters(category=category, name_contains=name_contains)
        return await ctx.deps.catalog_service.count_items(filters)

    @agent.tool
    async def list_items(
        ctx: RunContext[CatalogAssistantDeps], payload: ListCatalogItemsToolInput
    ) -> list[CatalogToolItem]:
        """List catalog items matching the given filters, ordered by name."""
        items = await ctx.deps.catalog_service.list_items(payload.filters, payload.limit)
        return [CatalogToolItem.model_validate(item, from_attributes=True) for item in items]

    return agent
```

`retries` stays at the library default. It budgets tool-argument and output validation retries — the `ModelRetry` loop that lets the model correct a malformed tool call — and never provider or transport errors, which surface on the first attempt whatever the budget says. `retries=0` therefore turns one malformed tool call, a routine model event, into a 500.

Agent-level `ModelSettings` carries what the workload needs: `max_tokens` from the response contract, and `thinking` as the unified effort level when the workload wants reasoning. Leave `temperature` and the other sampling settings out of it, because providers disagree on what to do with them: OpenAI and Anthropic drop them client-side with a warning once reasoning is on, Anthropic's newest models drop them whether reasoning is on or not, and Bedrock forwards them verbatim and leaves the provider to reject the call. Set sampling per workload once the target model is known, on the `Model` in the registry.

## Instructions

```python
CATALOG_ASSISTANT_INSTRUCTIONS = """
You are a read-only assistant for a service catalog API.

Rules:
- Use `count_items` for questions asking "how many", totals, or counts.
- Use `list_items` for questions asking for examples, names, or lists.
- Stay within the catalog domain. If the question is unrelated, refuse politely.
- Be concise and factual.
""".strip()
```

`instructions=` is the house default because instructions belong to the agent that is running: they go on the wire once per turn, and a different agent resuming the same conversation sends its own. `system_prompt=` parts are replayed from `message_history`, so a history that already carries one shadows the current agent's prompt and the model reads the stale text. Use `system_prompt=` only when replaying the original prompt is the point.

Write instructions as rules ("Use `count_items` for counts") rather than descriptions ("You can count items"), and name the case where no tool should be called.

## Tool schemas

A tool definition is a prompt the model reads before choosing. The docstring summary line becomes the tool description; keep it to one line saying what the tool does. Where the argument descriptions come from depends on how the arguments are declared:

- Plain parameters, as in `count_items`, take theirs from a Google-style `Args:` block, which pydantic-ai parses into the parameter schema.
- A single `BaseModel` parameter is flattened into the tool schema: `payload` disappears and the model's own fields become the tool's parameters. The parameter name is invisible to the model, so an `Args:` entry for it documents a name nobody sees. Put the prose in `Field(description=...)` on the model instead.

```python
from pydantic import BaseModel, Field

from app.domains.catalog.schemas import CatalogListFilters


class ListCatalogItemsToolInput(BaseModel):
    filters: CatalogListFilters = Field(
        default_factory=CatalogListFilters, description='Restrict the listing by category and by name substring.'
    )
    limit: int = Field(default=20, ge=1, le=100, description='Maximum number of items to return.')


class CatalogToolItem(BaseModel):
    sku: str
    name: str
    category: str
```

Constraints travel with the field: `ge`/`le` reach the model as `minimum`/`maximum`, which is cheaper than asking for the bound in prose.

## Model registry

Callers choose a model by an abstract name, never by a provider model id.

```python
from enum import StrEnum


class AssistantModelName(StrEnum):
    DEFAULT = 'default'
    FAST = 'fast'
```

The concrete ids are plain `str` fields in `Settings` (`ASSISTANT_DEFAULT_MODEL_ID`, `ASSISTANT_FAST_MODEL_ID`), so pointing the service at a model released next week is an environment change rather than a code change. `app/infrastructure/llms/registry.py` maps each name to a constructed `Model`, and the enum enters the HTTP contract in `schemas_api.py`, which is where the agent dependency reads the choice from:

```python
from pydantic import BaseModel, Field

from app.core.enums import AssistantModelName


class CatalogAssistantRequest(BaseModel):
    model: AssistantModelName
    question: str = Field(min_length=1, max_length=2_048)


class CatalogAssistantResponse(BaseModel):
    answer: str = Field(min_length=1)
```

The agent's `output_type` lives here with the HTTP contract because it usually is the response. When the endpoint adds a field of its own, keep the agent's model as the base and derive the response from it (`class CatalogConversationResponse(CatalogAssistantResponse): conversation_id: UUID`), so the agent never learns about HTTP.

Load `reference/providers.md` for the registry itself, provider wiring, provider-specific settings on the `Model`, `FallbackModel` failover, and mapping provider errors to HTTP status codes.

## Agent as a FastAPI dependency

```python
from typing import Annotated

from fastapi import Depends
from pydantic_ai import Agent

from app.domains.catalog_assistant.schemas import (
    CatalogAssistantDeps,
    CatalogAssistantRequest,
    CatalogAssistantResponse,
)
from app.infrastructure.llms.registry import get_model_registry, ModelRegistry


async def get_catalog_assistant_agent(
    payload: CatalogAssistantRequest,
    model_registry: Annotated[ModelRegistry, Depends(get_model_registry)],
) -> Agent[CatalogAssistantDeps, CatalogAssistantResponse]:
    return build_catalog_assistant_agent(model_registry[payload.model])
```

The route injects the agent alongside the service and stays thin, as in `fastapi-service`:

```python
router = APIRouter(tags=['Catalog Assistant'])

CatalogAssistantAgent = Annotated[
    Agent[CatalogAssistantDeps, CatalogAssistantResponse], Depends(get_catalog_assistant_agent)
]


@router.post('/assistants/conversations')
async def create_response(
    payload: CatalogAssistantRequest,
    service: Annotated[CatalogAssistantService, Depends()],
    agent: CatalogAssistantAgent,
) -> CatalogAssistantResponse:
    return await service.answer(payload, agent)
```

Declaring `payload` in both the route and the dependency does not add a second body field; FastAPI dedupes the read and the OpenAPI request body stays a bare `$ref`. Keep the dependency `async def` so it is not dispatched to a threadpool for a dict lookup.

Rebuilding the agent per request is what buys per-request model selection, and it keeps the agent reachable through `agent.override()` in tests. The alternative is one module-level agent built at import time with the model chosen per call (`agent.run(question, model=registry[payload.model], deps=...)`); take it when the model is fixed per deployment. The service takes the agent as a method argument rather than a constructor collaborator because it is chosen per request from `payload.model`, while the service's own constructor is resolved before the body is read.

## Running the agent

```python
from typing import Annotated

from fastapi import Depends
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from app.domains.catalog.service import CatalogService
from app.domains.catalog_assistant.schemas import (
    CatalogAssistantDeps,
    CatalogAssistantRequest,
    CatalogAssistantResponse,
)

CATALOG_ASSISTANT_USAGE_LIMITS = UsageLimits(request_limit=5)


class CatalogAssistantService:
    def __init__(self, catalog_service: Annotated[CatalogService, Depends()]) -> None:
        self._catalog_service = catalog_service

    async def answer(
        self,
        payload: CatalogAssistantRequest,
        agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse],
    ) -> CatalogAssistantResponse:
        result = await agent.run(
            payload.question,
            deps=self._build_deps(),
            usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS,
        )
        return result.output

    def _build_deps(self) -> CatalogAssistantDeps:
        return CatalogAssistantDeps(catalog_service=self._catalog_service)
```

`request_limit` caps the model requests one run may make, so a model that keeps calling the same tool stops instead of looping. Exceeding it raises `UsageLimitExceeded`; map it to 503 in `app/core/exception_handlers.py`, because the request was well formed and a 4xx would tell the caller to fix something that is not wrong. `UsageLimits` also carries `tool_calls_limit`, `output_tokens_limit`, `total_tokens_limit` and `cost_limit`, all raising the same `UsageLimitExceeded`; add one when a tool is expensive or the answer has a hard size budget.

## Reference files

- `reference/conversations.md` — multi-turn runs with `message_history`, the conversation endpoint that persists and resumes a transcript, and streaming an answer. Load it when the endpoint remembers previous turns or streams its response.
- `reference/testing.md` — blocking real provider calls, the reusable test-agent fixture, fixed answers with `TestModel`, failures and tool-call sequences with `FunctionModel`, and per-test overrides. Load it when writing or fixing agent tests.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `system_prompt=` on a new agent | `instructions=` | A history carrying a system prompt shadows the agent's own, so the model reads the stale one |
| `retries=0` to make failures surface | Leave `retries` at the default | It budgets validation retries only; zero turns one malformed tool call into a 500, and provider errors are never retried anyway |
| `temperature` in the agent's `ModelSettings` | Set sampling per workload on the `Model` | One provider drops it with a warning, another forwards it into a rejected call |
| `isinstance(model, BedrockConverseModel)` in the builder to add provider flags | Pass `settings=` to the `Model` in the registry | The builder stays provider-agnostic, and model-level settings merge under the agent's |
| Provider model ids as `Literal[...]` in `Settings` | Plain `str` fields | A new model id becomes an environment change instead of a code change |
| Importing a service inside a tool | Take it from `ctx.deps` | A module-level import cannot be substituted in a test |
| A tool with no docstring, or an `Args:` entry for a single `BaseModel` parameter | One-line docstring plus `Field(description=...)` on the model | The flattened parameter name never reaches the model, so its `Args:` entry documents nothing |
| Handling `openai.RateLimitError` or `botocore.ClientError` in the app | Handle `ModelHTTPError` and `ModelAPIError` | pydantic-ai normalizes provider API errors, so the SDK ones never arrive; Bedrock transport failures (botocore's `BotoCoreError`) are the exception and still need a catch-all |
| `agent.run(...)` with no `usage_limits` | Pass `UsageLimits(request_limit=...)` | The library default is 50 model requests per run; set a limit the endpoint can actually afford |

## Gotchas

- `CatalogAssistantService` reaches the route as `Annotated[CatalogAssistantService, Depends()]`, so it may take only injectable `__init__` parameters; `fastapi-service` explains what an ordinary defaulted parameter does to the endpoint.
- `Agent(instrument=True)` no longer exists and raises `TypeError`. Use `Agent.instrument_all(...)`, `agent.instrument = ...`, or `capabilities=[Instrumentation()]`.
- `agent.override()` takes `model`, `deps`, `toolsets`, `tools`, `native_tools`, `instructions`, `model_settings` and `retries` among others, but not `output_type` — that one is a per-run argument, `agent.run(..., output_type=str)`.
