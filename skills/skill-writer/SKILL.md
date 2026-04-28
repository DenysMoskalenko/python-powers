---
name: skill-writer
description: >
  Use when creating, editing, splitting, or reviewing `skills/<name>/SKILL.md`
  files in this repository, or when adding evaluation scenarios for those
  skills. Applies only to this repository's `skills/` tree; for foreign skill
  systems use that system's own authoring guide.
---

# Skill Writer (This Repository Only)

Meta-skill for authoring skills in this repository's `skills/` folder. Captures the house style so future edits reproduce the existing look, scope, and quality without re-deriving conventions.

> Scope: applies ONLY to `skills/<name>/SKILL.md` inside this repository.
> For other skill systems (`~/.cursor/skills/`, `~/.codex/skills/`, obra superpowers, etc.), refuse and point the user to that system's own authoring skill.

**Related**: none — this meta-skill is used alone when authoring or editing other skills. It references the domain skills by name in the ownership table.

## When to use

Load this skill when:
- Creating a new `skills/<name>/SKILL.md`
- Editing or extending any existing skill under `skills/`
- Splitting a skill into `SKILL.md` + `reference/*.md`
- Reviewing a skill for consistency before committing
- Adding or updating evaluation scenarios

**Do not load** for:
- Writing Python application code — use the domain skills (`python-code-style`, `fastapi-service`, etc.)
- Authoring skills outside `skills/` (different conventions apply)
- Non-skill documentation (README, AGENTS.md, plain notes)

## House style

### Folder layout

```text
skills/
  <skill-name>/
    SKILL.md              # required, discoverable
    reference/            # optional; loaded only when SKILL.md points here
      <topic>.md
```

Skill name: lowercase, hyphens only, descriptive (`python-testing`, not `tests`).

### Frontmatter

```yaml
---
name: <kebab-case-name>
description: >
  Use when <trigger 1>, <trigger 2>, or <trigger 3> — <concrete scope items
  separated by commas, written as keyword bait an agent would search for>.
  [Optional] For <adjacent topic> see `<sibling-skill>`.
---
```

Rules:
- `name` — lowercase + hyphens, matches folder name
- `description` — folded YAML scalar (`>`), 30-55 words, well under the 1024-char ceiling
- Description MUST start with "Use when…" and state **triggers**, not a workflow recipe
- Description in **third person** only ("Use when…", not "I help you…")
- Disambiguation clause is **optional** and earns its place only when:
  - A sibling skill could plausibly be confused with this one (use a positive `For X see \`sibling-skill\`` pointer), or
  - The skill is the broadest in its area and prone to over-application (use a "Does not cover X" exclusion)
  - If the skill name + topics already exclude the topic, do NOT add a "Does not cover X" line — it is dead weight paid on every skill-discovery decision
- Avoid pairing a "Use when…" sentence with an "Apply when…" sentence that just restates the same triggers
- No `compatibility:` field — put `> Requires ...` in the body instead
- No other frontmatter keys

### Body skeleton

Every `SKILL.md` follows this order. Sections in **bold** are mandatory.

```markdown
# <Title>

<One-paragraph overview — what this skill owns, 1-3 sentences>

> Requires <python version>, <key libraries>.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `<skill1>`, `<skill2>`, `<skill3>`.

## When to use        <!-- MANDATORY -->

Load this skill when:
- <specific, unambiguous trigger 1>
- <trigger 2>
- <trigger 3>

[Optional sibling pointer:] For <adjacent topic> use `<sibling-skill>`. For <other adjacent topic> use `<other-sibling>`.

## <domain sections>  <!-- MANDATORY: at least 2 -->

<Content: workflow, patterns, one excellent code example per pattern>

## Red Flags — STOP    <!-- MANDATORY for discipline skills; optional for technique skills -->

| About to… | Rule to apply |
|---|---|
| <rationalization or mistake> | <named rule> |

## Gotchas             <!-- MANDATORY -->

- <non-obvious behavior, edge case, or common misunderstanding>
```

### Discipline vs technique skills

| Type | Definition | Red Flags section |
|---|---|---|
| **Discipline** | Encodes rules agents rationalize around under pressure (e.g., `python-code-style`, `python-testing`) | REQUIRED |
| **Technique** | Teaches how to do a task with concrete steps (e.g., `python-tooling`) | OPTIONAL |
| **Domain** | Framework / library patterns (e.g., `fastapi-service`, `postgres-database`, `ai-agents`) | REQUIRED |

### Line budget

| File | Target | Hard limit |
|---|---|---|
| `SKILL.md` body | ≤ 300 lines | 500 lines |
| Each topical `reference/<topic>.md` | ≤ 200 lines | 300 lines |

If `SKILL.md` exceeds 300 lines, move the largest cohesive block (usually testing patterns or provider-specific details) into `reference/<topic>.md` and leave a one-line pointer.

`reference/evaluation-scenarios.md` is the central regression index and may exceed the topical reference limit; keep each scenario terse.

### Code examples

- Every code block gets a language tag (`python`, `bash`, `yaml`, `toml`, `markdown`, or `text`)
- **One excellent example per pattern** — not three mediocre ones
- Strip narrating comments (`# import the module`, `# return the result`)
- Use `app/` as the package name; do not use `your_app`, `your_project`, or similar placeholders

### Authoring references

- Load `reference/anthropic-best-practices.md` when deciding what stays inline, what moves to `reference/`, how strict a workflow should be, or how to structure validation loops.
- Load `reference/persuasion-principles.md` only for discipline/domain rules agents may rationalize around under pressure. Use it to tighten Red Flags; do not use it to add motivational fluff.
- Load `reference/evaluation-scenarios.md` before and after editing a skill. Treat it as the regression surface for this repository's skills.

### Description examples

Good and bad descriptions — most author mistakes happen here.

| Bad | Why | Better |
|---|---|---|
| `Use for tests — write a factory, POST, assert status.` | Workflow summary | Start with `Use when…` and list test triggers |
| `I help you write API tests.` | First person | Third person only |
| `Use for testing stuff.` | Vague | Include concrete terms agents search for |
| `Does not cover general Python style...` on `postgres-database` | Dead-weight exclusion | Drop exclusions the name already excludes |
| `Use when writing tests. Apply when updating tests.` | Duplicate trigger | Merge into one sentence |

For full authoring guidance, use `reference/anthropic-best-practices.md`.

## Composition and anti-overlap

**Content ownership** — when writing or editing a skill, confirm the content is not owned by another skill in this table:

| Topic | Owner | Forbidden in |
|---|---|---|
| Type hints, naming, DI rules, class layout, architecture principles, fail-fast | `python-code-style` | all others |
| uv / ruff / ty / pytest / pre-commit configuration and commands | `python-tooling` | all others |
| API-level tests, polyfactory, FastAPI dependency-override utilities, coverage | `python-testing` | all others |
| Routes, services, schemas, exception handlers, app factory | `fastapi-service` | `postgres-database`, `ai-agents` |
| SQLAlchemy models, queries, Alembic migrations, testcontainers setup | `postgres-database` | `fastapi-service`, `ai-agents` |
| pydantic-ai agents, tools, model registry, TestModel / FunctionModel patterns | `ai-agents` | `fastapi-service`, `postgres-database` |

**Composition** — which skills load together for which task:

| Task | Load alongside `python-code-style` |
|---|---|
| Add CRUD endpoint with DB | `fastapi-service` + `postgres-database` |
| Add AI agent endpoint | `ai-agents` + `fastapi-service` |
| Write or update tests | `python-testing` + relevant domain skill(s) |
| Set up tooling / CI / Makefile | `python-tooling` |
| Write a migration | `postgres-database` |
| Refactor for style compliance | (nothing — `python-code-style` alone is enough) |

**All domain skills assume `python-code-style` is in effect. They must NOT re-state its rules.**

## Skill edit validation loop

Use RED-GREEN-REFACTOR for new skills and meaningful edits:

1. **RED.** Read existing scenarios first. For new behavior, add or identify a scenario that fails without the rule. Capture the exact mistake or rationalization the skill must prevent.
2. **GREEN.** Make the smallest skill edit that addresses that failure. Prefer one rule, one table row, or one reference pointer over broad rewrites.
3. **REFACTOR.** Re-check line budget, Red Flags, Gotchas, and evaluation scenarios. If a new rationalization appears, add an explicit counter and re-check.

## Workflow: Creating a new skill

Follow each step in order. Skipping steps produces the skill-drift problem that this skill exists to prevent.

1. **Brainstorm triggers.** Write one sentence per scenario where a developer would want this skill. If you cannot produce 3+ distinct, concrete triggers, the skill is too narrow — absorb the content into an existing skill instead.

2. **Check overlap.** Compare scope against the ownership table above. If >30% of the planned content would belong to an existing skill, extend that skill instead of creating a new one. If the skill genuinely occupies an empty area, proceed.

3. **Draft the description.** 30-55 words. Start with "Use when…". State triggers, not workflow. Add a disambiguation clause ONLY when a sibling skill could plausibly be confused (positive `For X see \`sibling\`` pointer) or this skill is the broadest in its area and prone to over-application ("Does not cover X" exclusion). If the name + topics already exclude a topic, do not list it. Iterate until no recipe leaks into the triggers and no token is wasted.

4. **Draft the body.** Follow the skeleton exactly. Keep one excellent code example per pattern. If any single section exceeds 200 lines, plan to move it to `reference/<topic>.md` (step 6).

5. **Write Red Flags + Gotchas.** For discipline/domain skills, build a rationalization table (`About to X` → `Apply rule Y`). Think specifically: what would an agent DO wrong without this skill? Use those exact mistakes as row entries.

6. **Split if over budget.** If `SKILL.md` exceeds 300 lines, move the largest cohesive section (commonly *testing*, *providers*, or *advanced patterns*) into `reference/<topic>.md`. Leave a one-line pointer: "See `reference/<topic>.md` for…".

7. **Write evaluation scenarios.** Add 3-4 scenarios to `reference/evaluation-scenarios.md` under a new `## <skill-name>` heading. Use the format (Prompt / Must produce / Must not produce) described in that file.

8. **Cross-reference.** Add a `**Related**:` line to the new SKILL.md listing skills that compose with it. Then audit every existing SKILL.md's `**Related**:` line and add the new skill where relevant (usually 1-3 additions).

9. **Stage in git.** Per the user rule, run `git add skills/<name>/` so the new files aren't lost. Do not commit unless explicitly asked.

## Workflow: Editing an existing skill

1. **Locate the rule.** Which section owns the behavior you are changing? Refuse to duplicate content into adjacent sections.

2. **Diff the intent.** If the change expands the skill's scope, re-check the ownership table. Sometimes the right edit is to move content to a different skill, not add it here.

3. **Apply minimal change.** Do not rewrite adjacent sections that are unrelated to the edit. Preserve surrounding structure, formatting, and terminology.

4. **Re-verify against evaluation scenarios.** Read the `## <skill-name>` section of `reference/evaluation-scenarios.md`. If your change would cause any scenario to fail, either adjust your change or update the scenario with a clear reason documented in the commit/diff.

5. **Stage in git.** `git add skills/<name>/SKILL.md` plus any reference file you touched.

## Red Flags — STOP

These mean you are about to violate the house style. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Write a description that summarizes workflow ("Use X to write a factory, then POST…") | Description = triggers ONLY, never a recipe |
| Add a "Does not cover X" line listing topics the name already excludes | Disambiguation is optional — earn it (sibling-confusion risk or broad over-application risk) or leave it out |
| Pair "Use when…" with "Apply when…" that restates the same triggers | Pick one; merge into a single sentence |
| Add a `compatibility:` frontmatter field | Put `> Requires ...` in the body instead |
| Write a first-person description ("I help you…") | Third person only |
| Skip the `## When to use` section | Mandatory skeleton element |
| Repeat a `python-code-style` rule inside a domain skill | Domain skills assume `python-code-style`; never re-state it |
| Duplicate tooling commands across skills | Only `python-tooling` owns commands |
| Exceed 300 lines in `SKILL.md` without splitting | Move to `reference/<topic>.md` |
| Write a SKILL.md without a `**Related**:` line | Mandatory skeleton element |
| Use `your_app` / `your_project` placeholders | Use `app` + the standard substitution note |
| Create a skill without ≥3 concrete triggers | The skill is too narrow; extend an existing one instead |
| Add a new skill without evaluation scenarios | Scenarios are part of the deliverable, not optional |
| Copy a rule into two skills "for convenience" | Single source of truth per topic |
| Narrate changes in code comments | Code should be self-documenting; narrating comments are banned in examples too |

## Common mistakes

**1. Description that summarizes the skill's workflow.**
Agent reads the description, takes the summary as the instruction, and never opens the skill body. Fix: description = when, not how.

**2. Skill with one trigger.**
If the skill only applies to a single, narrow task (e.g., "use when setting up pytest-asyncio"), the content should be a section inside a broader skill, not a new one. Fix: expand scope or absorb.

**3. Dumping reference docs into `SKILL.md`.**
A long `SKILL.md` slows every load. Fix: main file teaches patterns + workflow; reference files hold exhaustive detail.

**4. Adding "also consider X" escape hatches.**
"You could also use pypdf, PyMuPDF, or pdfplumber" creates paralysis. Fix: one default + one escape hatch for a specific case (e.g., "pdfplumber; for scanned PDFs use pdf2image + tesseract").

**5. Using real dates or version numbers in prose.**
"As of January 2026, SQLAlchemy 2.0.45 supports…" ages badly. Fix: use capability language ("recent SQLAlchemy versions support…") or cite the required version once in the `> Requires` line.

**6. Inconsistent terminology within a skill.**
Mixing "endpoint", "route", and "path" in the same skill confuses the agent. Fix: pick one term per concept and search/replace.

## Gotchas

- Adding a new skill means auditing ALL siblings' `**Related**:` lines and adding the new skill where it composes
- `description` is injected into the system prompt — if triggers are vague, the skill does not load when needed
- `reference/*.md` files are NEVER auto-loaded; the main `SKILL.md` must link to them by path
- Changes to `python-code-style` affect every domain skill's assumptions — review all siblings after editing it
- `reference/evaluation-scenarios.md` doubles as a regression test — read it before AND after editing any skill
- This skill follows its own rules. If you edit THIS skill, re-run its own Red Flags table against the diff

## See also

- `reference/evaluation-scenarios.md` — spot-check scenarios per existing skill plus the format spec for writing new ones
