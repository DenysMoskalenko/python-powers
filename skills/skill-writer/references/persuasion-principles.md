# Persuasion Principles for Skill Design

Use this only to make critical skill rules harder to rationalize away. Do not add motivational copy or fake urgency.

## When to use

Use persuasion principles for skills that:

- Enforce discipline under pressure
- Have compliance costs agents may avoid
- Prevent repeated known failure modes
- Need bright-line Red Flags

Do not use them for pure reference/API docs.

## Practical principles

| Principle | Use in skills | Avoid |
|---|---|---|
| Authority | `MUST`, `Never`, `No exceptions` for hard rules | Heavy authority for ordinary guidance |
| Commitment | Required announcements, explicit choices, checklists | Vague "consider tracking this" language |
| Scarcity | `Before proceeding`, `immediately after`, ordered gates | False urgency |
| Social proof | "Every time", "X without Y fails" for known patterns | Unsupported claims |
| Unity | "This repository", "our house style" for shared conventions | Sycophancy or agreement-seeking |
| Reciprocity | Rarely useful in skills | Guilt or obligation framing |
| Liking | Do not use for compliance | Friendly fluff that weakens rules |

## How to tighten a rule

Weak:

```markdown
Consider writing tests before implementation when feasible.
```

Tight:

```markdown
Write implementation before the failing test? Stop. Delete it and restart from the test. No exceptions.
```

For this repository, prefer precise Red Flags:

| About to... | Rule to apply |
|---|---|
| Keep untested code as "reference" while writing scenarios | Delete means delete; reference code biases the scenario |
| Add "just one exception" to a domain skill | Single source of truth per topic |

## Checks before adding pressure

- Is the rule genuinely critical?
- Does this serve the user's actual quality goal?
- Is there a known rationalization this wording blocks?
- Would a calmer reference sentence work just as well?

If the answer to the last question is yes, keep the calmer sentence.
