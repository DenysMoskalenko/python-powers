---
name: python-code-style
description: Use when writing, reviewing, or refactoring Python 3.13+ application or library code for readability or structure — type hints and PEP 695 aliases, model-first data design, naming conventions, dependency injection, early returns, fail-fast discipline, and architecture principles (KISS, YAGNI, SRP, DRY). For ruff and formatter configuration see `python-tooling`.
---

# Python Code Style

House rules for production Python: how to type it, how to shape data, how to name things, and which default wins when two designs both read well. Where a rule is a house default rather than an invariant, the sentence names the case for departing from it. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires Python 3.13+.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-tooling`, `python-testing`, `fastapi-service`, `postgres-database`, `ai-agents`, `project-scaffolding`.

## Type Hints

Type every public function, method, and class attribute; annotations are the documentation the type checker can verify.

- Builtin generics and union syntax: `list[int]`, `dict[str, int]`, `str | None`. The `typing` spellings `List`, `Dict`, and `Tuple` are deprecated aliases of the builtins; `Optional` and `Union` are not deprecated, but ruff's `UP007` rewrites them to the operator form.
- PEP 695 syntax for aliases and generics — `type SortingOrder = Literal['asc', 'desc']`, `def first[ItemT](items: Sequence[ItemT]) -> ItemT | None` — rather than `TypeAlias`, which is deprecated, or a module-level `TypeVar`.
- `collections.abc` for `Callable`, `Sequence`, `Mapping`, `Iterable`, `Generator`, and `AsyncGenerator`; `typing` for `Annotated`, `Literal`, `Protocol`, `TypedDict`, `Self`, `Unpack`, and `TYPE_CHECKING`. Ask parameters for the least you need (`Sequence[str]`, `Mapping[str, int]` when you only read them) and return the concrete type (`list[str]`).
- `Any` belongs at an untyped third-party boundary and nowhere else; narrow it on the next line, because inside your own code the type exists and can be found.
- `object` is the correct hint for a value you only pass through or must narrow before use — `__eq__(self, other: object)`, a logging sink, a cache key — and unlike `Any` it leaves type checking switched on. Do not use it to avoid modelling an interface you already know; that case wants a `Protocol` or a type parameter.

## Model-First Data

Structured data travels as a model rather than a raw `dict` — a raw mapping only when the keys are unknown at design time, such as user-supplied metadata — so its shape is declared once and checked everywhere it is used.

- Pydantic `BaseModel` at every boundary — HTTP payloads, external API responses, configuration, anything crossing a process edge — so validation and serialization live in the same declaration.
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

A value drawn from a fixed set is typed as that set, not as `str` — including a set defined by a third party, which you mirror as your own enum instead of passing their strings around. Use `Literal` when the values are local to one field or alias, and `StrEnum` (as `BookFormat` above) when they are reused across modules, iterated over, or more than about three. A set that changes without a change on your side — provider model ids, regions, SKUs from an external catalogue — is not fixed: keep it a validated `str` and let configuration carry the value.

## Naming Conventions

The domain skills assume these names, so keep them even in a module that holds only one of each.

- `<Entity>Model` for SQLAlchemy classes (`AuthorModel`), which leaves the bare `<Entity>` name for the pydantic schema callers see.
- `<Entity>`, `<Entity>Create`, and `<Entity>Patch` for schemas, with `_<Entity>Base` as the module-private base holding the shared fields. `<Entity>Update` is reserved for a full-replacement PUT body, which most endpoints never have.
- `*Error` for domain exceptions (`NotFoundError`, `InvalidPriceError`), all subclassing one base per package.
- `from logging import getLogger` at the top of the module, then `_logger = getLogger(__name__)` below the imports. Log messages are f-strings like the rest of the code; structured fields go under `extra={'extra': {...}}`, which `fastapi-service` explains.
- A leading `_` marks anything private to its module or class: helpers, attributes, base classes; `_validate_*` raises when an invariant is broken, `_apply_*` transforms and returns. Names say what the value is: `deleted_author_id`, not `result`.

## Dependency Injection and Class Layout

A class takes its collaborators as constructor parameters and stores them; it never builds one itself, because a caller who cannot substitute a collaborator cannot test or reconfigure the class. Anything that varies by environment or by test is a collaborator: a clock, an HTTP client, storage, a source of randomness. Framework DI (`Depends()` in FastAPI, see `fastapi-service`) is the same rule written in the framework's syntax.

Order the body `__init__`, public methods in the order a caller meets them, then private helpers — a reader needs the interface before the machinery, so `@staticmethod` helpers sit with the other private methods rather than at the top.

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

Validate at the boundary — route schema, constructor, factory — so everything behind it can trust its inputs instead of re-checking them. When an invariant breaks, raise on the spot.

- Return or raise early on the invalid or trivial case, so the main path continues unindented at the top level of the function. Drop the `else` after a branch that already returned or raised; it only indents the rest of the body.
- Raise a domain error class (one base per package, `app/core/exceptions.py` in a service, translated to HTTP by `fastapi-service`) rather than a bare `ValueError`, so callers and handlers can tell causes apart.
- Chain exceptions with `raise ... from exc`; the original traceback is usually the useful half. Prefer raising over returning `None` or a sentinel, which spreads the check to every caller.
- Catch the specific exception you can actually handle. `except Exception: pass` turns a bug into wrong data with no trace of where it started.
- Keep secrets out of logs and exception messages: `SecretStr` in settings, and mask account or card numbers before formatting them.

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

When you need behaviour that does not exist yet, take the first option that fits:

1. Code already in this project — extend it slightly instead of writing a near-duplicate.
2. The standard library.
3. A dependency the project already installs.
4. The smallest local implementation that covers the case you have.
5. A new maintained dependency, when the local implementation would be large or risky — parsing, crypto, protocols; let uv resolve the version, never guess one, and say in your report that the lock file changed.

Business rules unique to the domain are always local code. Prefer the smallest coherent change to what exists, and introduce an extension seam — a protocol, a strategy parameter, a subclass hook — only when a second implementation or a recurring variation already exists, because one implementation behind an interface costs every reader and pays nobody back. A `Protocol` that names the interface a constructor parameter needs (`ReportStorage` above) is not a speculative seam; the ban is on variants nobody asked for.

Do not reshape production modules to serve a one-off script, migration, or operational task; keep that logic inside the script. A new parameter or a changed signature in shared code needs a recurring application need behind it.

## No Utils Modules

Do not add `utils.py`, `helpers.py`, `common.py`, or `shared.py`. They collect unrelated functions and nobody can predict what is inside them. Every function has a real home: the service that uses it, the module that owns its type, or a module named after the concept (`app/core/schemas.py`). When no home fits, the abstraction is wrong — fix that rather than opening a drawer. In a project that already has such a drawer, add to it only when the function belongs with its neighbours; do not create a second catch-all and do not relocate the existing one unasked.

## Helpers and Comments

Extract a helper when it hides a named sub-step or removes a repeated transformation, so the public method reads as a short sequence of business steps. Do not extract a wrapper that only forwards its arguments; it adds a hop and hides nothing.

Comment the why, not the what. `# Check if the author exists` above `if author is None` ages into noise, while `# The vendor rejects batches over 50 ids, so chunk even when the caller passes fewer` saves the next reader a git-blame session. Tradeoffs, external constraints, and workarounds earn a line; restating the code does not.

## Architecture Principles

When two designs both work, this order decides:

1. **KISS** — the simplest thing that solves the problem in front of you.
2. **YAGNI** — no code for a requirement nobody has asked for.
3. **Single responsibility** — one class, one job, one reason to change.
4. **DRY** — one source of truth, applied on the third repetition; two similar blocks are cheaper than the wrong abstraction.
5. **Encapsulation** — state hidden behind `_`, behaviour exposed.
6. **Loose coupling** — depend on the narrow interface you use, and take it as a parameter.

## Follow Project Style

Before changing existing code, read the enclosing function, class, and module, plus the call sites and tests that depend on it. A quoted line or a pasted snippet does not carry enough context to tell whether the change is correct; when the line is already right in its surroundings, say so and change nothing.

One way of doing things beats two better ways. Match the file you are in — signatures, naming, error handling, layout — instead of introducing a parallel style for the code you happen to write.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `dict[str, Any]` for a shape you know | A pydantic model, or a frozen dataclass for internal values | The shape is declared once and every call site is checked against it |
| `Any` because the real type is awkward | The real type, or `object` narrowed with `isinstance` before use | `Any` disables checking for everything it touches; `object` leaves it on |
| `Optional[str]`, `List[int]`, `TypeAlias` | `str \| None`, `list[int]`, `type Alias = ...` | `List`/`TypeAlias` are deprecated; `Optional` is the spelling `UP007` rewrites |
| A new `utils.py` or `helpers.py` | The module that owns the concept, or `app/core/<concept>.py` | A named module stays findable; a catch-all grows without limit |
| A bare `str` where the values come from a fixed set | `Literal` for one field, `StrEnum` when reused or iterated | Typos become type errors instead of runtime bugs |
| Constructing a collaborator inside a class | Take it as a constructor parameter | A caller or a test cannot substitute what the class builds itself |
| `except Exception: pass` | Catch the specific error and raise a domain error `from exc` | A silent except converts a bug into wrong data |
| Patching a line quoted in the request without opening the file | Read the enclosing function and its call sites first | The quoted line is often correct and the real fault is elsewhere |

## Gotchas

- `Sequence[str]` also matches a plain `str`, so a caller who passes one string type-checks and then iterates characters. Use `list[str]` where that would be a bug.
- `@dataclass(slots=True)` returns a new class object, so zero-argument `super()` inside its methods raises `TypeError`, and a frozen dataclass cannot inherit from a non-frozen one. Keep slotted value objects free of inheritance.
- `StrEnum` members compare equal to their string value (`BookFormat.EBOOK == 'ebook'` is `True`). Convenient for JSON round-trips, and occasionally the reason an assertion passes when it should not.
- A `TYPE_CHECKING`-only import is safe in a SQLAlchemy `Mapped['OtherModel']` forward reference, which the declarative registry resolves, but not in a pydantic field annotation: pydantic evaluates annotations when the class is built, so the model stays incomplete until the name is imported for real or `model_rebuild()` runs where it exists.
- `type Alias = ...` is evaluated lazily, so a forward reference inside one is fine, but code that inspects the alias at runtime needs `Alias.__value__` rather than the alias object.
