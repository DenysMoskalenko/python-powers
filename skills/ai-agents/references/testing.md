# Testing pydantic-ai Agents

Reference for testing agents built with the patterns in `SKILL.md`. Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- Block real model requests globally
- Test-agent fixture using `TestModel`
- Deterministic responses with `FunctionModel`
- Test-scoped model overrides

## Block real model requests globally

In `pytest_configure`, disable real LLM calls before any agent import so accidental real API calls fail loudly:

```python
import pytest
from pydantic_ai import models as pydantic_ai_models


def pytest_configure(config: pytest.Config) -> None:
    pydantic_ai_models.ALLOW_MODEL_REQUESTS = False
```

## Test-agent fixture using TestModel

Override the agent dependency with a test agent built on `TestModel`:

```python
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from app.domains.catalog_assistant.agents import build_catalog_assistant_agent, get_catalog_assistant_agent
from app.domains.catalog_assistant.schemas import CatalogAssistantDeps, CatalogAssistantResponse
from tests.dependencies import temporary_override


def generate_test_agent[AgentDeps, AgentOutput](
    app: FastAPI,
    dependency: Callable[..., Agent[AgentDeps, AgentOutput]],
    agent_builder: Callable[[Model], Agent[AgentDeps, AgentOutput]],
) -> Iterator[Agent[AgentDeps, AgentOutput]]:
    agent = agent_builder(TestModel())
    with temporary_override(app, dependency, lambda: agent):
        yield agent


@pytest.fixture(scope='function')
def test_catalog_assistant_agent(app: FastAPI) -> Iterator[Agent[CatalogAssistantDeps, CatalogAssistantResponse]]:
    yield from generate_test_agent(app, get_catalog_assistant_agent, build_catalog_assistant_agent)
```

`generate_test_agent` is reusable — one line per agent fixture.

## Deterministic responses with FunctionModel

`FunctionModel` lets you return exact responses without going through `TestModel`'s inference:

```python
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def build_mock_model(response: BaseModel) -> FunctionModel:
    def _cb(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(info.output_tools) != 1:
            raise AssertionError('Expected one output tool')
        part = ToolCallPart(tool_name=info.output_tools[0].name, args=response.model_dump(mode='json', by_alias=True))
        return ModelResponse(parts=[part])

    return FunctionModel(_cb)


def build_raising_model(exc: Exception) -> FunctionModel:
    def _cb(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise exc
    return FunctionModel(_cb)
```

Pass the agent's declared response model to `build_mock_model`. It sends one tool call, using the field aliases shared by validation and serialization. If those aliases differ, supply the keys the output tool accepts. For a union with multiple output tools, select the intended tool by name in the test and assert the returned type. Two output models can have identical field names.

## Test-scoped model override

Use `agent.override(model=...)` to swap the model for a single test. The `with` block restores the original model afterwards:

```python
from httpx2 import AsyncClient
from pydantic_ai import Agent

from app.domains.catalog_assistant.schemas import CatalogAssistantResponse


class TestCatalogAssistantResponse:
    async def test_success(self, client: AsyncClient, test_catalog_assistant_agent: Agent) -> None:
        answer = 'There are 3 matching items.'
        with test_catalog_assistant_agent.override(model=build_mock_model(CatalogAssistantResponse(answer=answer))):
            response = await client.post(
                '/v1/assistants/conversations',
                json={'model': 'gpt-6.1-sol', 'question': 'How many matching items do we have?'},
            )
        assert response.status_code == 200
        assert response.json() == {'answer': answer}
```

## Gotchas

- `ALLOW_MODEL_REQUESTS = False` must be set before any agent import — otherwise agent modules with import-time side effects can still reach the provider.
- Set `retries=0` on agents (shown in `SKILL.md`) so failures surface immediately in tests rather than being masked by retries.
