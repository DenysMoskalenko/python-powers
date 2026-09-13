# Conversations and Streaming

Multi-turn runs, persisting a conversation between requests, and streaming an answer to the client. The single-shot request/response agent is in `SKILL.md`; examples continue the `catalog_assistant` domain and use `app/` as the top-level package.

## Contents

- Multi-turn runs
- Persisting a conversation
- The conversation endpoint
- Streaming
- Gotchas

## Multi-turn runs

A run returns its messages, and the next run takes them as `message_history`:

```python
first = await agent.run(question, deps=deps, usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS)
second = await agent.run(
    follow_up, deps=deps, message_history=first.all_messages(), usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS
)
```

`all_messages()` is the running transcript — the history the run was given plus what it added — so the same line still carries turn one when it is written for turn three. `new_messages()` holds only what this run added.

Earlier turns' instructions are stored with the history but ignored; the agent sends its current text on every turn, so an edit to the instruction text takes effect on the next turn of every conversation already in flight, including one resumed from storage.

## Persisting a conversation

Messages are Pydantic models, and `ModelMessagesTypeAdapter` serializes them without a hand-written schema:

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter

stored = ModelMessagesTypeAdapter.dump_json(result.all_messages())
history = ModelMessagesTypeAdapter.validate_json(stored)
```

Store the bytes as JSON, keyed by whatever identifies the conversation. A run that was given the history returns it inside `all_messages()`, so storing that keeps one write path for the first turn and every later one. Reach for `new_messages()` only where the transcript is appended to without being loaded — an append-only log, or an SQL update that concatenates onto the stored bytes.

Reasoning models return opaque continuation state — thinking blocks, reasoning items — inside those messages. Round-trip them through the type adapter and hand them back verbatim; do not filter, rewrite or reorder message parts to make a transcript prettier.

## The conversation endpoint

The store is ordinary domain state: a table keyed by conversation id, or a module-level dict while the service is single-process. The id is the service's own, not the model's, and the route that resumes a conversation takes it as a path parameter. Both methods go beside `answer` on the service from `SKILL.md`, and `CatalogConversationResponse` is the agent's output model with that id added.

```python
from uuid import UUID, uuid4

from pydantic_ai.messages import ModelMessagesTypeAdapter

from app.core.exceptions import NotFoundError
from app.domains.catalog_assistant.schemas import CatalogConversationResponse

_CONVERSATIONS: dict[UUID, bytes] = {}


class CatalogAssistantService:
    async def start_conversation(
        self,
        payload: CatalogAssistantRequest,
        agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse],
    ) -> CatalogConversationResponse:
        conversation_id = uuid4()
        result = await agent.run(payload.question, deps=self._build_deps(), usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS)
        _CONVERSATIONS[conversation_id] = ModelMessagesTypeAdapter.dump_json(result.all_messages())
        return CatalogConversationResponse(conversation_id=conversation_id, **result.output.model_dump())

    async def continue_conversation(
        self,
        conversation_id: UUID,
        payload: CatalogAssistantRequest,
        agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse],
    ) -> CatalogConversationResponse:
        stored = _CONVERSATIONS.get(conversation_id)
        if stored is None:
            raise NotFoundError(f'Conversation(id={conversation_id}) not found')
        result = await agent.run(
            payload.question,
            deps=self._build_deps(),
            message_history=ModelMessagesTypeAdapter.validate_json(stored),
            usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS,
        )
        _CONVERSATIONS[conversation_id] = ModelMessagesTypeAdapter.dump_json(result.all_messages())
        return CatalogConversationResponse(conversation_id=conversation_id, **result.output.model_dump())
```

`NotFoundError` and the 404 handler that maps it belong to `fastapi-service`: an unknown conversation id is an ordinary domain not-found, not a model failure.

The creating route is the one in `SKILL.md` with `status_code=status.HTTP_201_CREATED` and `CatalogConversationResponse` as its return type, because it now creates a resource. The route that continues the conversation answers 200 and reads the id from the path:

```python
@router.post('/assistants/conversations/{conversation_id}/messages')
async def continue_conversation(
    conversation_id: UUID,
    payload: CatalogAssistantRequest,
    service: Annotated[CatalogAssistantService, Depends()],
    agent: CatalogAssistantAgent,
) -> CatalogConversationResponse:
    return await service.continue_conversation(conversation_id, payload, agent)
```

## Streaming

`run_stream` is an async context manager, and its text deltas feed a `StreamingResponse` directly. This method goes beside `answer` on the same service and assembles its deps through the same `_build_deps()`; `AsyncGenerator` comes from `collections.abc`:

```python
class CatalogAssistantService:
    async def stream_answer(
        self,
        payload: CatalogAssistantRequest,
        agent: Agent[CatalogAssistantDeps, CatalogAssistantResponse],
    ) -> AsyncGenerator[str]:
        async with agent.run_stream(
            payload.question,
            deps=self._build_deps(),
            output_type=str,
            usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS,
        ) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk
```

```python
@router.post('/assistants/conversations/stream')
async def stream_response(
    payload: CatalogAssistantRequest,
    service: Annotated[CatalogAssistantService, Depends()],
    agent: CatalogAssistantAgent,
) -> StreamingResponse:
    return StreamingResponse(service.stream_answer(payload, agent), media_type='text/plain')
```

`output_type=str` at the run level is what makes the text exist. The agent's declared output type is a structured model delivered through an output tool, and a tool call carries no text to stream — the same agent object can answer one endpoint with a structured object and another with a stream because `output_type` is a per-run argument.

`delta=True` yields each new fragment; the default yields the whole text so far on every chunk, which a client appending fragments will duplicate. Chunks are also debounced — grouped over a short window so validation does not run per token — so a fast model can arrive as one chunk; pass `debounce_by=None` to forward each fragment as it lands. When the client needs tool calls or thinking events rather than plain text, open `agent.run_stream_events(...)` as an async context manager and iterate the handle it yields (`async with agent.run_stream_events(...) as events:`).

## Gotchas

- The usage limits apply per run, not per conversation. A long conversation makes as many runs as it has turns, so cap the number of stored turns if a caller can extend one indefinitely.
- An exception raised after the first chunk cannot change the status code, because the response is already committed as 200. Everything that can fail cleanly — request validation, model selection — happens before the stream opens.
