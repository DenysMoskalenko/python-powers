# Testing pydantic-ai Agents

How to test the agent patterns in `SKILL.md` without reaching a provider: blocking real requests, the reusable test-agent fixture, fixed answers, injected failures, and per-test overrides. Load this when writing or fixing agent tests. `python-testing` owns the surrounding test layout, the `client` and `app` fixtures, and `temporary_override`; examples use `app/` as the top-level package.

## Contents

- Block real provider calls
- The test-agent fixture
- Fixed answers with `TestModel`
- Failures with `FunctionModel`
- Per-test overrides
- Instrumentation
- Gotchas

## Block real provider calls

Turn the global switch off so a test that accidentally holds a real provider model fails loudly instead of spending money. This is the line this skill contributes to the `pytest_configure` skeleton `python-testing` owns:

```python
pydantic_ai_models.ALLOW_MODEL_REQUESTS = False
```

The flag is read when a request is about to go out, not when a module is imported, so import order does not matter and a real provider model can be constructed freely in a test — it fails only if something runs it, with `RuntimeError: Model requests are not allowed, since ALLOW_MODEL_REQUESTS is False`. `TestModel` and `FunctionModel` are exempt. A test that deliberately drives a real client over a mocked transport re-enables it locally with `override_allow_model_requests(True)`.

## The test-agent fixture

The agent reaches the app through a FastAPI dependency, so a test agent is one built on `TestModel` installed over that dependency. One generic helper serves every agent in the service:

```python
from collections.abc import Awaitable, Callable, Generator

from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from tests.dependencies import temporary_override


def generate_test_agent[AgentDeps, AgentOutput](
    app: FastAPI,
    dependency: Callable[..., Awaitable[Agent[AgentDeps, AgentOutput]]],
    agent_builder: Callable[[Model], Agent[AgentDeps, AgentOutput]],
) -> Generator[Agent[AgentDeps, AgentOutput]]:
    agent = agent_builder(TestModel())
    with temporary_override(app, dependency, lambda: agent):
        yield agent
```

Each agent then costs one fixture, and the type parameters carry the agent's deps and output type through to the test signature:

```python
@pytest.fixture
def test_catalog_assistant_agent(app: FastAPI) -> Generator[Agent[CatalogAssistantDeps, CatalogAssistantResponse]]:
    yield from generate_test_agent(app, get_catalog_assistant_agent, build_catalog_assistant_agent)
```

Because the fixture yields the agent object the app will use, a test can swap the model again for its own case with `agent.override(...)`.

The fixture replaces the agent dependency, so the dependency's own body — the registry lookup — never runs under it. Cover that once by overriding the registry instead, which is also what catches a second agent wired to the wrong registry. The two constants below are used by every test in this file:

```python
from app.core.enums import AssistantModelName
from app.infrastructure.llms.registry import get_model_registry, ModelRegistry

CONVERSATIONS_URL = '/v1/assistants/conversations'
QUESTION = 'How many hardware items?'


async def test_the_agent_dependency_reads_the_registry(app: FastAPI, client: AsyncClient) -> None:
    registry: ModelRegistry = {AssistantModelName.DEFAULT: TestModel(custom_output_args={'answer': 'ok'})}
    with temporary_override(app, get_model_registry, lambda: registry):
        response = await client.post(CONVERSATIONS_URL, json={'model': 'default', 'question': QUESTION})

    assert response.status_code == 200
    assert response.json() == {'answer': 'ok'}
```

## Fixed answers with `TestModel`

`TestModel` fills the output type with generated data by default, which is enough for a schema check. For an exact answer, hand it the payload and stop it calling tools:

```python
async def test_success(
    client: AsyncClient, test_catalog_assistant_agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse]
) -> None:
    answer = 'There are 2 hardware items.'
    mock_model = TestModel(
        custom_output_args=CatalogAssistantResponse(answer=answer).model_dump(mode='json'), call_tools=[]
    )
    with test_catalog_assistant_agent.override(model=mock_model, native_tools=[]):
        response = await client.post(CONVERSATIONS_URL, json={'model': 'default', 'question': QUESTION})

    assert response.status_code == 200
    assert response.json() == {'answer': answer}
```

`custom_output_args` resolves the output tool itself, so nothing in the test has to match a tool by name, index or schema. `custom_output_text` does the same for a plain-text run. Write no hand-rolled `ModelResponse` for a fixed answer.

## Failures with `FunctionModel`

`FunctionModel` runs a callback in place of the model, which is how a test produces a failure or a specific sequence of tool calls:

```python
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel


def build_raising_model(exc: Exception) -> FunctionModel:
    def _cb(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise exc

    return FunctionModel(_cb)
```

Raise the exception the app actually handles — pydantic-ai's normalized `ModelHTTPError` or `ModelAPIError`, never a provider SDK exception, which production code never sees:

```python
async def test_provider_rate_limit_maps_to_429(
    client: AsyncClient, test_catalog_assistant_agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse]
) -> None:
    exc = ModelHTTPError(status_code=429, model_name='test')
    with test_catalog_assistant_agent.override(model=build_raising_model(exc)):
        response = await client.post(CONVERSATIONS_URL, json={'model': 'default', 'question': QUESTION})

    assert response.status_code == 429
```

`reference/providers.md` covers the handler side of that mapping, and the harder test that drives a real provider SDK over a mocked transport to prove the normalization.

A callback that returns a `ToolCallPart` on every turn instead of raising is how a runaway tool loop is tested against `UsageLimits`. To let a run finish instead, the callback calls the output tool by the name pydantic-ai gave it, which arrives on `AgentInfo`:

```python
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.domains.catalog_assistant.schemas import CatalogAssistantResponse


def build_tool_then_answer_model() -> FunctionModel:
    turns = 0

    def _cb(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal turns
        turns += 1
        if turns == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name='count_items', args={'category': 'hardware'})])
        [tool_return] = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
        args = CatalogAssistantResponse(answer=f'There are {tool_return.content} hardware items.').model_dump(
            mode='json'
        )
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_cb)
```

`messages[-1]` on the second turn is the `ModelRequest` carrying the tool's `ToolReturnPart`, so answering from it proves the tool ran and reached `ctx.deps`; filtering the parts by type is also how a test reads a replayed history, where the same list holds tool calls and user prompts. Returning invalid arguments on the first output-tool call and valid ones on the second is how the default retry budget is tested.

## Per-test overrides

`agent.override(...)` is scoped to its `with` block and restores what was there before. It also takes `native_tools=[]`, which drops provider native tools that `TestModel` cannot emulate — use it unless the test is specifically about native-tool wiring:

```python
with test_catalog_assistant_agent.override(model=TestModel(), native_tools=[]):
    ...
```

`output_type` is not an override argument; pass it to the run instead (`agent.run(question, deps=deps, output_type=str)`).

## Instrumentation

`Agent(instrument=True)` no longer exists. Switch tracing on globally with `Agent.instrument_all(...)`, per agent with `agent.instrument = ...` or `capabilities=[Instrumentation()]` from `pydantic_ai.capabilities.instrumentation`, and leave it off in unit tests unless the span is what is being asserted.

## Gotchas

- `TestModel` calls every registered tool once before producing output, so a test that asserts on a service call gets one call per tool for free — and a tool that mutates state runs in tests that never meant to exercise it. Pass `call_tools=[]` when the tools are not the subject.
- `TestModel.last_model_request_parameters` holds the `ToolDefinition` list the model was given after a run, which is how a test asserts that a tool's description and parameter schema reached the model.
- `FunctionModel`'s `AgentInfo` carries `instructions`, the exact instruction text sent for that turn; asserting on it is how instruction and message-history behaviour is pinned down without a provider.
