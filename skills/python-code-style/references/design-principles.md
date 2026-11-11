# Design Principles

How the principles in `SKILL.md` turn into decisions while writing or reviewing code. The list order is the
priority: when two principles pull in different directions, the earlier one wins (KISS over DRY, YAGNI over
Open/Closed).

No principle here removes validation at a trust boundary, error handling that prevents data loss, a security
check, or a test for risky logic.

Contents:
- KISS
- YAGNI
- Single Responsibility
- DRY
- Encapsulation, Loose Coupling, Open/Closed, Fail Fast

## KISS — the plainest code that does the job

Every layer of indirection is something the next reader has to open and hold in their head.

You are about to break it when you:
- write a base class and subclasses for two or three cases that a `match` or a mapping covers;
- add a registry, factory, or plugin point that has one entry;
- re-check at runtime what the boundary schema already validated or ty already proves.

Test: does each layer the reader must open make a decision, or only pass the call along?

```python
class Exporter(ABC):  # Bad: a class hierarchy for two formats
    @abstractmethod
    def export(self, rows: list[ReportRow]) -> str: ...


class CsvExporter(Exporter): ...


class JsonExporter(Exporter): ...


def export_rows(rows: list[ReportRow], export_format: ExportFormat) -> str:  # Good: ty flags an unhandled member
    match export_format:
        case ExportFormat.CSV:
            return _to_csv(rows)
        case ExportFormat.JSON:
            return REPORT_ROWS_ADAPTER.dump_json(rows).decode()
```

Not this: KISS is not "fewest lines". A clear name and one extracted helper beat a dense one-liner.

## YAGNI — build only what the request needs

Unrequested code is code nobody asked to review, test, or maintain.

You are about to break it when you:
- carry over a neighbouring feature's validator or business rule the request does not mention;
- add `--dry-run`, a retry, a cache, or a config switch to a run-once script;
- invent a policy the request did not state (rounding, clamping, a default value).

Test: does the request, an input it accepts, or a safety rule need this line? If not, leave it out; if the
request left the choice open, name the choice in your reply.

Request: "add `convert(amount, rate)`".

```python
def convert(amount: Decimal, rate: Decimal) -> Decimal:  # Bad: a rounding policy nobody asked for
    return (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def convert(amount: Decimal, rate: Decimal) -> Decimal:  # Good
    return amount * rate
```

Reply: "No rounding: the request does not say how to round."

Not this: YAGNI does not skip what the request needs in order to work. A new endpoint still gets its schema
bounds, its domain exceptions, and its tests. Nor does it forbid refactoring that eases the next change.

## Single Responsibility — one reason to change

When one unit answers to two unrelated reasons, a change for one breaks the other.

You are about to break it when you:
- parse a third-party response and apply a business rule in the same method;
- put two groups' rules in one class: finance's invoice layout and sales' discount rule.

Test: list who could ask for a change to this code. Two unrelated askers (the provider changes its format, the
business changes its rule) mean two units.

```python
class PricingService:  # Bad: the provider's wire format and the pricing rule in one method
    async def quote(self, sku: str) -> Quote:
        response = await self._http.get(f'/prices/{sku}')
        amount = Decimal(response.json()['amount'])
        return Quote(sku=sku, price=amount * (1 + VAT_RATE))


class PriceClient:  # Good: the client owns the wire format
    async def get_price(self, sku: str) -> ProviderPrice:
        response = await self._http.get(f'/prices/{sku}')
        response.raise_for_status()
        return ProviderPrice.model_validate_json(response.content)


class PricingService:  # Good: the service owns the rule
    async def quote(self, sku: str) -> Quote:
        price = await self._price_client.get_price(sku)
        return Quote(sku=sku, price=price.amount * (1 + VAT_RATE))
```

Not this: a responsibility is a reason to change, not a line count. Do not split one cohesive service into a
class per method (see `Break Down Complexity`).

## DRY — one source of truth for one rule

Duplicated knowledge drifts apart: one copy gets the fix and the other keeps the bug.

You are about to break it when you:
- compute the same business rule (a price with VAT, an eligibility check) in two places;
- or, the opposite mistake, merge two pieces of code because they look alike although they answer to different
  rules.

Test: if one copy changes, must the other change too, for the same reason? Yes: one rule, give it one home now.
No: keep both, however alike they look. Unsure: keep the copies until a third shows which.

```python
NAME_MAX_LENGTH = 64  # Bad: one constant ties two unrelated limits together


class AuthorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)


class TagCreate(BaseModel):
    label: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)


class AuthorCreate(BaseModel):  # Good: each limit belongs to its own column
    first_name: str = Field(min_length=1, max_length=64)


class TagCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64)
```

Shortening tag labels to 32 must not shorten author names. `VAT_RATE` above is the opposite case: one rate,
one constant, every price computed from it.

Not this: in tests, repeat setup and assertions when it makes each test readable on its own (`python-testing`).

## Encapsulation, Loose Coupling, Open/Closed, Fail Fast

- **Encapsulation**: see `Class Layout`. Callers use the public methods; service and client state
  (`_session`, `_http`) and helpers take a `_` prefix. Pydantic model fields stay public: pydantic treats
  `_name` as a private attribute, not a field.
- **Loose Coupling**: see `Dependency Injection`. The injected parameter is the seam, so inject the concrete
  class. Add a `Protocol` when a second implementation arrives (a fake that a test passes in directly counts).
  With one implementation it is indirection the reader follows for nothing; framework DI already lets tests
  swap the real class.
- **Open/Closed**: a new variant costs one arm in the one `match` that owns the choice, or a new function or
  module, and no edits to callers. When the same `match` repeats elsewhere, replace both with a mapping or a
  class per variant. A small extension to an existing function follows `Reuse Before Creating`.
- **Fail Fast**: see `Fail Fast, Fail Loud`.
