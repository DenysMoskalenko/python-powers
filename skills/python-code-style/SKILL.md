---
name: python-code-style
description: >
  Use when writing, reviewing, or refactoring Python 3.13+ code — type hints,
  code density, model-first data design, naming, dependency injection, early
  returns, fail-fast discipline, and architectural principles (KISS, YAGNI,
  SRP, DRY). Does not cover framework patterns, tool configuration, or test
  layout — those are owned by the matching domain skill.
---

# Python Code Style

Rules for writing production-quality Python. Every rule here reflects a deliberate choice — follow them unless you have a specific, stated reason not to.

> Requires Python 3.13+.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `python-tooling`, `python-testing`, `fastapi-service`, `postgres-database`, `ai-agents`.

## When to use

Load this skill for any Python edit. It's a prerequisite for the domain skills (`fastapi-service`, `postgres-database`, `ai-agents`), which assume these rules are in effect and do not re-state them.

## Type Hints

Type every public function, method, and class attribute. Types are documentation that the toolchain can verify.

**Modern syntax only** (Python 3.13+) — use builtin generics (`list[int]`, `dict[str, int]`, `tuple[int, ...]`) and union syntax (`str | None`, `str | int`). Never import `List`, `Dict`, `Optional`, `Union`, `Tuple` from `typing`. Use `typing` only for types that have no builtin equivalent: `Annotated`, `TypeAlias`, `Literal`, `TypeVar`, `Protocol`, `TypedDict`, `Unpack`, `Generator`, `AsyncGenerator`, `TYPE_CHECKING`.

**Never use `Any`** unless the value is genuinely unconstrained. If you reach for `Any` because you don't know the type, stop and find it. `Any` disables type checking for everything it touches.

**Never use `object`** in type hints or code. If you think you need it, the actual type is either a protocol, a base class, or a generic.

```python
from typing import Annotated, Literal, TypeAlias

SortingOrder: TypeAlias = Literal['asc', 'desc']

class AuthorService:
    def __init__(self, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
        self._session = session

    async def get_author_by_id(self, author_id: int) -> Author:
        ...
```

## Code Density

Prefer fewer lines when the result is equally readable. Don't split into 3 lines what fits cleanly on 1. Let ruff handle line breaks — write the compact version and the formatter will split it if it exceeds the line length.

Never leave trailing whitespace. Ruff and pre-commit should remove it automatically, but don't introduce formatting noise on purpose.

```python
return Author.model_validate(author)

result = Author.model_validate(author)
return result
```

This does not mean "cram everything onto one line." Readability wins. But don't add vertical space just because you can.

## Model-First Data

Always use a data model (pydantic `BaseModel`, `dataclass`, `attrs`, `NamedTuple`, `TypedDict`) for structured data. Never pass raw `dict` when the shape is known.

Raw `dict` is acceptable only for genuinely dynamic/generic mappings — e.g., a function that accepts arbitrary key-value config.

```python
class AuthorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=64)
    last_name: str = Field(min_length=1, max_length=64)
```

## Enumerate Known Values

When a value comes from a predefined set, represent it as `StrEnum` or `Literal` — never a bare `str`. This applies equally to internal constants and external contracts. If a third-party API defines an enum in its schema, mirror it as a typed enum in yours.

Decision rule:

```text
Small, local, tied to one field or TypeAlias?           → Literal
Reused across modules, needs iteration, or > 3 values?  → StrEnum
```

```python
from enum import StrEnum
from typing import Literal, TypeAlias

class AIModelName(StrEnum):
    GPT_5_4 = 'gpt-5.4'
    SONNET_4_6 = 'sonnet-4.6'

SortingOrder: TypeAlias = Literal['asc', 'desc']
```

## Dependency Injection

Inject dependencies via constructor parameters or framework DI (`Depends()`). Never instantiate collaborators inside a class. This applies broadly, not just to FastAPI.

```python
class AuthorService:
    def __init__(self, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
        self._session = session
```

## Library-First

Before writing custom code, search for an existing library that solves the problem. Evaluate by: maintenance activity, community size, API fit.

Custom code is justified only when:
- The logic is domain-specific business rules unique to your application
- Performance-critical paths need control that libraries don't provide
- Security-sensitive code requires full auditability
- No library exists after thorough evaluation

When adding a library, always use the latest version. Never guess version numbers.

## No Utils Modules

Never create `utils.py`, `helpers.py`, `common.py`, or `shared.py`. These become dumping grounds that grow indefinitely with unrelated functions.

Every function belongs somewhere specific — in the service it supports, in a shared `core/` module, or colocated with the feature. If you can't find a home for a function, that's a design signal — rethink the abstraction.

## Self-Documenting Code

Code should be readable without comments. Achieve this through:
- Descriptive function names: `_validate_author_unique` not `_check`
- Descriptive variable names: `deleted_author_id` not `result`
- Small functions with single purpose

**Don't comment the obvious.** Never write `# Check if author exists` above `if author is None`. The code says that already.

**Do comment the non-obvious.** Explain *why* when the reason isn't clear from context:
- Tradeoffs: why this approach over alternatives
- Constraints: external requirements that shaped the code
- Workarounds: what's being worked around and why

```python
include_exception_handlers(_app)
```

## Break Down Complexity

When logic starts branching, extracting, or repeating, split it into smaller reusable functions. Prefer two or three focused functions over one long method with mixed concerns.

Extract helpers when they:
- Hide a clear sub-step (`_apply_filters`, `_validate_author_unique`, `_build_response`)
- Remove repeated conditionals or transformations
- Make the public method read like a short sequence of business steps

Do not extract tiny wrappers with no semantic value. The goal is simpler code, not more files or more indirection.

## Class Layout

Public methods first, private methods after. This puts the class interface — what callers interact with — at the top where it's immediately visible.

```python
class AuthorService:
    async def get_author_by_id(self, author_id: int) -> Author: ...
    async def list_authors(self, ...) -> Page[Author]: ...
    async def create_author(self, creation: AuthorCreate) -> Author: ...
    async def update_author(self, author_id: int, updates: AuthorUpdate) -> Author: ...
    async def delete_author_by_id(self, author_id: int) -> None: ...

    def _apply_filters(self, query: Select, filters: AuthorListFilters) -> Select: ...
    @staticmethod
    def _apply_sorting(query: Select, sorting: AuthorListSorting) -> Select: ...
    async def _validate_author_unique(self, ...) -> None: ...
```

## Early Returns

Prefer early returns over nested conditions. Exit the function as soon as you know the answer.

```python
async def get_author_by_id(self, author_id: int) -> Author:
    author = await self._session.scalar(query)
    if author is None:
        raise NotFoundError(f'Author(id={author_id}) not found')
    return Author.model_validate(author)

async def get_author_by_id(self, author_id: int) -> Author:
    author = await self._session.scalar(query)
    if author is not None:
        return Author.model_validate(author)
    else:
        raise NotFoundError(f'Author(id={author_id}) not found')
```

## Fail Fast, Fail Loud

Validate at boundaries. Services assume their inputs are valid; the boundary (route schema, factory, constructor) enforces that.

- Raise specific domain exceptions immediately when invariants are violated
- Never swallow errors — `except Exception: pass` is a bug hiding in plain sight
- Prefer raising over returning `None` or a sentinel to signal failure
- Never log secrets — use `SecretStr`, mask card numbers, strip tokens before logging
- Use `chain from` (`raise DomainError(...) from exc`) to preserve the original cause

```python
if not account_number.isdigit() or len(account_number) != 16:
    raise ValueError('Invalid account number')

try:
    result = await self._provider.charge(amount, account_number)
except ProviderError as exc:
    raise PaymentFailedError(f'Charge failed: {exc}') from exc
```

Fail fast pairs with model-first: Pydantic/dataclass validation at the boundary makes the body of your function trust its inputs.

## Architecture Principles

Non-negotiable defaults, priority order:

1. **KISS** — simple, readable solutions over clever ones
2. **YAGNI** — don't build for hypothetical future needs
3. **Single Responsibility** — one class, one job, one reason to change
4. **DRY** — one source of truth, but don't DRY prematurely (wait for the third repetition)
5. **Encapsulation** — hide internal state (`_` prefix), expose behavior
6. **Loose Coupling** — depend on abstractions, inject dependencies
7. **Open/Closed** — extend via new classes or composition, not editing existing code
8. **Fail Fast** — validate at boundaries, never swallow errors (see section above)

## Modern Python

Use the latest language features. Python 3.13+ is the target.

- `uuid.uuid7()` over `uuid.uuid4()` when available (ordered, better for DB indexes)
- f-strings for all string formatting
- `match` statements when they improve readability over `if/elif`
- `pathlib.Path` over `os.path`
- `datetime.now(UTC)` over `datetime.utcnow()`

## Reuse Before Creating

Before writing a new function, check if an existing one does nearly the same thing. If it does, extend the existing function slightly rather than creating a near-duplicate.

Excessive patterns become a maintenance burden. Understand the project's existing style and follow it rather than introducing parallel approaches.

## Don't Bend Production Code for One-Off Needs

Never modify core application modules to support a one-time script, migration, or operational task. Write self-contained logic inside the script instead.

Adding parameters, changing signatures, or introducing abstractions in shared code must be justified by a recurring application need — not a single ad-hoc use case. Long-lived production code is stable infrastructure; protect it.

## Follow Project Style

When joining an existing codebase, read how services, routes, and tests are written. Match the existing patterns — function signatures, naming, file organization, error handling approach.

Introducing a different style for "your" code creates inconsistency that multiplies maintenance cost. One way of doing things is better than two "better" ways.

## Red Flags — STOP

These mean you are about to violate a rule above. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Type `Any` because "the type is complex" | Type Hints — find the real type |
| Type `object` anywhere | Type Hints — use a protocol or generic |
| Create `utils.py` / `helpers.py` / `common.py` | No Utils Modules |
| Use `dict[str, Any]` for a known shape | Model-First Data |
| Pass a bare `str` where values come from a fixed set | Enumerate Known Values |
| Instantiate a collaborator inside a class | Dependency Injection |
| Write `except Exception: pass` | Fail Fast, Fail Loud |
| Write a retry/cache/datetime helper by hand | Library-First |
| Nest `if author is not None:` over two levels | Early Returns |
| Add a comment that narrates what the next line does | Self-Documenting Code |
| Put private methods before public methods | Class Layout |
| Hand-write a migration instead of `alembic ... --autogenerate` | `postgres-database` skill |

## Gotchas

- `str | None` requires Python 3.10+ at runtime; you already target 3.13 — this is fine. The older `Optional[str]` form still works but is banned.
- `StrEnum` members compare equal to their string value (`AIModelName.GPT_5_4 == 'gpt-5.4'` is `True`). Useful for JSON round-trips, occasionally surprising in asserts.
- `TypeAdapter(list[X])` is the idiomatic way to validate a list of pydantic models — see `postgres-database` for the full pattern.
- `Annotated[Service, Depends()]` with an empty `Depends()` triggers FastAPI auto-injection of the service's own dependencies.
