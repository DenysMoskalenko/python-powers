---
name: python-code-style
description: Use when writing, reviewing, or refactoring Python 3.13+ application or library code for readability or structure — type hints and PEP 695 aliases, model-first data design, naming conventions, dependency injection, early returns, fail-fast discipline, and architecture principles (KISS, YAGNI, SRP, DRY). For ruff and formatter configuration see `python-tooling`.
---

# Python Code Style

House rules for production Python: how to type it, shape data, name things, and which default wins when two designs both read well. An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires Python 3.13+.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-tooling`, `python-testing`, `fastapi-service`, `postgres-database`, `ai-agents`, `project-scaffolding`.

## Type Hints

Type every public function, method, and class attribute; annotations are documentation the type checker verifies.

- Builtin generics and union syntax: `list[int]`, `dict[str, int]`, `str | None`. `List`, `Dict`, `Tuple` are deprecated aliases; `Optional` and `Union` are not, but ruff's `UP045` and `UP007` rewrite them to the operator form.
- PEP 695 for aliases and generics — `type SortingOrder = Literal['asc', 'desc']`, `def first[ItemT](items: Sequence[ItemT]) -> ItemT | None` — rather than the deprecated `TypeAlias` or a module-level `TypeVar`.
- `collections.abc` for `Callable`, `Sequence`, `Mapping`, `Iterable`, `Generator`, `AsyncGenerator`; `typing` for the rest. Ask parameters for the least you need (`Sequence[str]` when you only read it) and return the concrete type (`list[str]`).
- `Any` belongs at an untyped third-party boundary and nowhere else; narrow it on the next line. `object` is the hint for a value you only pass through or must narrow before use — `__eq__(self, other: object)`, a cache key — and unlike `Any` it leaves checking on. Do not use it to avoid modelling an interface you already know; that case wants a `Protocol` or a type parameter.

## Model-First Data

Structured data travels as a model, not a raw `dict`, so its shape is declared once and checked everywhere; a raw mapping only when the keys are unknown at design time (user-supplied metadata).

- Pydantic `BaseModel` at every boundary — HTTP payloads, external API responses, configuration — so validation and serialization live in one declaration.
- `@dataclass(frozen=True, slots=True, kw_only=True)` is the house default for internal value objects that need no validation: immutable, cheap, and keyword-only, so a new field cannot silently absorb a positional argument. Drop `frozen=True` for an object that is genuinely mutated in place.

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class BookFormat(StrEnum):
    HARDCOVER = 'hardcover'
    PAPERBACK = 'paperback'
    EBOOK = 'ebook'


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(gt=0)
    book_format: BookFormat


@dataclass(frozen=True, slots=True, kw_only=True)
class ShippingQuote:
    carrier: str
    cost: Decimal
```

## Enumerate Known Values

A value drawn from a fixed set is typed as that set, not as `str` — a third party's set included, mirrored as your own enum. `Literal` when the values are local to one field; `StrEnum` (as `BookFormat` above) when reused across modules, iterated, or more than about three. A set that changes without a change on your side — provider model ids, regions, external SKUs — is not fixed: keep it a validated `str` carried by configuration.

## Naming Conventions

The domain skills assume these names; keep them even in a module that holds only one of each.

- `<Entity>Model` for SQLAlchemy classes (`AuthorModel`), leaving the bare `<Entity>` for the pydantic schema callers see.
- `<Entity>`, `<Entity>Create`, `<Entity>Patch` for schemas, with `_<Entity>Base` as the module-private base holding the shared fields. `<Entity>Update` is reserved for a full-replacement PUT body, which most endpoints never have.
- `*Error` for domain exceptions (`NotFoundError`, `InvalidPriceError`), all subclassing one base per package.
- `from logging import getLogger` at the top of the module, then `_logger = getLogger(__name__)` below the imports. Messages are f-strings; structured fields go under `extra={'extra': {...}}`, which `fastapi-service` explains.
- A leading `_` marks anything private to its module or class; `_validate_*` raises when an invariant is broken, `_apply_*` transforms and returns. Names say what the value is: `deleted_author_id`, not `result`.

## Dependency Injection and Class Layout

A class takes its collaborators as constructor parameters and never builds one itself, because a caller who cannot substitute a collaborator cannot test or reconfigure the class. Anything that varies by environment or by test is a collaborator: a clock, an HTTP client, storage, randomness. `Depends()` in FastAPI (`fastapi-service`) is the same rule in framework syntax.

Order the body `__init__`, public methods in the order a caller meets them, then private helpers; a reader needs the interface before the machinery, so `@staticmethod` helpers sit with the other private methods rather than at the top.

```python
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol


class ReportStorage(Protocol):
    def rows(self, report_id: int) -> Sequence[str]: ...


class ReportService:
    def __init__(self, storage: ReportStorage, clock: Callable[[], datetime]) -> None:
        self._storage = storage
        self._clock = clock

    def render(self, report_id: int) -> str:
        rows = self._apply_redactions(self._storage.rows(report_id))
        return f'{self._clock().isoformat()}: {len(rows)} rows'

    def _apply_redactions(self, rows: Sequence[str]) -> list[str]:
        return [row for row in rows if not row.startswith('secret:')]
```

## Fail Fast

Validate at the boundary — route schema, constructor, factory — so everything behind it can trust its inputs; when an invariant breaks, raise on the spot.

- Return or raise early on the invalid or trivial case, so the main path continues unindented; drop the `else` after a branch that already returned or raised.
- Raise a domain error class (one base per package, `app/core/exceptions.py` in a service, translated to HTTP by `fastapi-service`) rather than a bare `ValueError`, so callers and handlers can tell causes apart.
- Chain with `raise ... from exc`. Prefer raising over returning `None` or a sentinel, which spreads the check to every caller.
- Catch the specific exception you can handle; `except Exception: pass` turns a bug into wrong data with no trace.
- Keep secrets out of logs and exception messages: `SecretStr` in settings; mask account or card numbers before formatting them.

```python
from decimal import Decimal, InvalidOperation

from app.core.exceptions import BaseServiceError


class InvalidPriceError(BaseServiceError):
    pass


def parse_price(raw: str) -> Decimal:
    try:
        price = Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidPriceError(f'Price is not a number: {raw!r}') from exc
    if price <= 0:
        raise InvalidPriceError(f'Price must be positive, got {price}')
    return price
```

## Reuse Before Creating

For behaviour that does not exist yet, take the first option that fits:

1. Code already in this project — extend it slightly instead of writing a near-duplicate.
2. The standard library.
3. A dependency the project already installs.
4. The smallest local implementation that covers the case you have.
5. A new maintained dependency when the local implementation would be large or risky — parsing, crypto, protocols; let uv resolve the version and report that the lock file changed.

Business rules unique to the domain are always local code. Introduce an extension seam — a protocol, a strategy parameter, a subclass hook — only when a second implementation or a recurring variation already exists; one implementation behind an interface costs every reader and pays nobody back (`ReportStorage` above names an interface a parameter needs, which is different). Do not reshape production modules to serve a one-off script or migration; keep that logic inside the script. A new parameter or a changed signature in shared code needs a recurring application need behind it.

## No Utils Modules

Do not add `utils.py`, `helpers.py`, `common.py`, or `shared.py`; they collect unrelated functions nobody can predict. Every function has a real home: the service that uses it, the module that owns its type, or a module named after the concept (`app/core/schemas.py`). When no home fits, the abstraction is wrong. In a project that already has such a drawer, add to it only when the function belongs with its neighbours; do not open a second one and do not relocate the existing one unasked.

## Helpers and Comments

Extract a helper when it hides a named sub-step or removes a repeated transformation, so the public method reads as a sequence of business steps; not a wrapper that only forwards its arguments. Prefer fewer lines when equally readable — `return Author.model_validate(author)`, not `result = ...` then `return result` — and let ruff split long lines.

Comment the why, not the what: `# Check if the author exists` above `if author is None` is noise; `# The vendor rejects batches over 50 ids, so chunk even when the caller passes fewer` saves a git-blame.

## Architecture Principles

When two designs both work, this order decides:

1. **KISS** — the simplest thing that solves the problem in front of you.
2. **YAGNI** — no code for a requirement nobody has asked for.
3. **Single responsibility** — one reason to change.
4. **DRY** — applied on the third repetition; two similar blocks are cheaper than the wrong abstraction.
5. **Encapsulation** — state behind `_`, behaviour exposed.
6. **Loose coupling** — depend on the narrow interface you use, taken as a parameter.

## Follow Project Style

Before changing existing code, read the enclosing function, class, and module, plus the call sites and tests; a quoted line does not carry enough context to judge the change, and when it is already right in its surroundings, say so and change nothing. One way of doing things beats two better ways: match the file you are in — signatures, naming, error handling, layout.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| A bare `str` where the values come from a fixed set | `Literal` for one field, `StrEnum` when reused | Typos become type errors instead of runtime bugs |
| Constructing a collaborator inside a class | Take it as a constructor parameter | A test cannot substitute what the class builds itself |

## Gotchas

- `Sequence[str]` also matches a plain `str`, so a caller passing one string type-checks and then iterates characters; use `list[str]` where that would be a bug.
- `@dataclass(slots=True)` returns a new class object, so zero-argument `super()` inside its methods raises `TypeError`, and a frozen dataclass cannot inherit from a non-frozen one; keep slotted value objects free of inheritance.
- `StrEnum` members compare equal to their string value (`BookFormat.EBOOK == 'ebook'` is `True`), occasionally the reason an assertion passes when it should not.
- A `TYPE_CHECKING`-only import works in a SQLAlchemy `Mapped['OtherModel']` forward reference (the declarative registry resolves it) but not in a pydantic field annotation: pydantic evaluates annotations when the class is built, so the model stays incomplete until the name is imported for real or `model_rebuild()` runs.
- `type Alias = ...` is evaluated lazily, so a forward reference inside one is fine, but code that inspects the alias at runtime needs `Alias.__value__`.
