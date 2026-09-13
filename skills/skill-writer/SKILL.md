---
name: skill-writer
description: Use when creating, editing, splitting, or reviewing a skill under this repository's `skills/` folder — folder layout, frontmatter, body skeleton, ownership boundaries, tone for current models, copy-ready examples, budgets, and the checks to run before handing off. Explicit-only; other skill systems have their own authoring guides.
disable-model-invocation: true
---

# Skill Writer (This Repository Only)

Meta-skill for authoring skills in this repository's `skills/` folder; it records the decisions the existing skills follow so edits reproduce the same shape. Other skill systems have their own authoring guides. It is explicit-only (`disable-model-invocation: true`); `AGENTS.md` step 6 tells agents to read it before touching a skill.

**Related**: none; the ownership table below names the domain skills.

Load `references/anthropic-best-practices.md` for the upstream limits behind a rule below.

## Who reads a skill, and what that changes

Skills are loaded by current frontier coding agents in Claude Code, Codex and Cursor. Their vendors' prompting guides agree on these points, and the rules below follow from them:

- They follow instructions literally and do not generalize scope on their own. Say "every `relationship()` in `app/infrastructure/db/models/`", not "relationships".
- They over-comply with emphatic language. Where you would write "CRITICAL: you MUST", write "Use X when Y".
- They reconcile contradictions at a cost, so one owner per rule.
- They already know the libraries. A paragraph earns its tokens only if the agent would get it wrong without it: a house decision, a fragile sequence, a gotcha.
- Reasons generalize better than bans. Put the why in the same sentence as the rule when it is not obvious.

## House style

### Folder layout

```text
skills/<skill-name>/
  SKILL.md               # required; loaded when the skill triggers
  references/<topic>.md  # optional; loaded only when SKILL.md points at it by path
  agents/openai.yaml     # required; Codex display metadata (interface.display_name, interface.short_description)
```

Skill name: lowercase, hyphens, matches the folder. No `README.md` inside a skill folder; human documentation is the repository `README.md`.

### Frontmatter

```yaml
---
name: <kebab-case-name>
description: Use when <trigger 1>, <trigger 2>, or <trigger 3> — <concrete keywords users type>. [Optional] For <adjacent topic> see `<sibling-skill>`.
---
```

- `description`: 30–60 words, under 400 characters; triggers first, then keywords, file names and pasted-error strings an agent would search for (Claude Code truncates the listing at 1,536 characters, Codex front-loads under an 8,000-character budget); third person; no workflow steps; no `<` or `>` anywhere in the frontmatter (claude.ai uploads reject them). Add a sibling pointer only when a real prompt could land on the wrong skill; no "Does not cover …" sentence for what the name already implies.
- Allowed keys: `name`, `description`, `disable-model-invocation`, `paths`, `when_to_use`, `metadata` (plus the spec's `license`/`compatibility`, which hosts accept but ignore). `> Requires …` stays in the body, which all three hosts show at use time.
- `disable-model-invocation: true` removes the skill from the host's listing (Claude Code and Cursor); Codex needs `policy.allow_implicit_invocation: false` in `agents/openai.yaml`. Keep the two in sync and reference such a skill by file path.

### Body skeleton

```markdown
# <Title>

<One paragraph: what this skill owns, in 1–3 sentences.> An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires <python version>, <key libraries>.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `<skill1>`, `<skill2>`.

## <domain sections>        <!-- at least two; one excellent example per pattern -->

## Common mistakes          <!-- recommended for domain and discipline skills -->

| Mistake | Do instead | Why |
|---|---|---|

## Gotchas                  <!-- required; the highest-value section -->
```

No `## When to use` section: the host routes on the description alone, so triggers in the body are paid on every load; extra sub-triggers go into `when_to_use`.

### Rule classes and tone

- **Invariant** (breaks the architecture if violated): state plainly. "Services raise domain exceptions; handlers translate them to HTTP."
- **House default** (valid alternatives exist): say so and name the escape hatch in the same sentence. "The house default is `selectinload` for collections; use `joinedload` for a to-one on a single-object fetch."
- **Heuristic** (needs measurement): give the signal. "Profile before switching loaders on a hot endpoint."

Write in plain imperatives: no capitalized emphasis, no "STOP", no "never … no exceptions" unless the exception really does not exist. Prefer "do X" over "don't do Y"; when a boundary must be negative, pair it with the positive alternative. No generic exhortations ("be thorough", "double-check"); current models over-apply them. A concrete procedure with a named artefact ("read the enclosing function and its call sites") is fine.

### Budgets

| File | House budget | Upstream limit |
|---|---|---|
| `SKILL.md` | 300 lines and 2,000 words (`wc -w`, code included; about 3k tokens) | 500 lines; 5,000 words (guide) or 5,000 tokens (spec) |
| `references/<topic>.md` | same, one cohesive topic, with a contents list above 100 lines | one level deep |

The word budget is the one that bites: 300 lines of 700-character paragraphs cost twice what the line count suggests. Move a cohesive block (setup, fixtures, providers) to `references/` when `SKILL.md` passes a budget or the block is used only in some tasks. Explain each rule once: a `## Common mistakes` row may name a body rule in one line as a scan index, but re-explaining it there, in a gotcha, or in a sibling skill "for convenience" is how a skill doubles in size without saying more.

### Code examples

- Every fence has a language tag. One excellent example per pattern.
- Copy-ready: every symbol is defined in the skill, imported from a named module, or noted as a sibling's. No `...` in parameter lists, no narrating comments.
- Verified: examples come from a scratch project generated from the BoilerplateBuilder template that passes its quality gate on current library versions; no unrun code.
- Neutral: no provider model ids, dates, or version numbers in prose; versions live once in `> Requires`. A measurement stays only when it is the evidence for a gotcha.

## Ownership and composition

One owner per topic. When a rule needs another skill's material to be complete, move it there instead of linking "see `<sibling>` for the full pattern".

| Topic | Owner | Not restated in |
|---|---|---|
| Type hints, naming, DI, class layout, architecture principles, fail-fast | `python-code-style` | all others |
| uv / ruff / ty / pytest config, commands, prek hooks, CI, warnings policy | `python-tooling` | all others |
| API-level tests, factories, test helpers, dependency-override utilities, coverage policy | `python-testing` | all others |
| Routes, service shape, schemas, exception handlers, settings, app factory, module layout | `fastapi-service` | `postgres-database`, `ai-agents` |
| SQLAlchemy models, loading strategy, query/pagination/filter helpers, Alembic, DB test fixtures | `postgres-database` | `fastapi-service`, `ai-agents` |
| pydantic-ai agents, tools, model registry, provider settings, agent test fixtures | `ai-agents` | `fastapi-service`, `postgres-database` |
| Greenfield generation from the template | `project-scaffolding` | all others |

Services own their queries, so `fastapi-service` shows the service shape with one lookup and `postgres-database` the full query patterns; the two must agree. Domain skills assume `python-code-style` is in effect and do not restate it; `README.md` lists the combinations a task loads together.

## Workflow

### Creating a skill

1. List three or more distinct, recurring triggers; fewer means the content belongs in an existing skill.
2. Check the ownership table; if about 30% or more of the content belongs elsewhere, extend that skill instead.
3. Write the description, then the body from the skeleton, with every example verified.
4. Try the description against 3–5 realistic prompts that should load the skill (casual phrasing, pasted errors, file names) and 2–3 near-misses that belong to a sibling; a skill that only loads when named needs more concrete keywords.
5. Add the skill to every sibling's `**Related**` line where it composes, to `README.md`, and to the manifests' keywords if it widens the plugin's scope.
6. `git add skills/<name>/` and any other file you created; leave modified files unstaged and do not commit.

### Editing a skill

1. Read the whole section you are changing, including the neighbouring example; if the quoted line is already right in context, say so and change nothing.
2. If the change widens scope, re-check the ownership table; the right edit may be in a sibling.
3. Make the smallest change that fixes the observed problem; add a rule only after a repeated failure, and say in the diff which failure it answers.
4. Run the checks below.
5. `git add` any file you created; leave modified files unstaged.

### Checks before handing off

```bash
claude plugin validate .                                        # .claude-plugin/marketplace.json only
wc -w -l skills/<name>/SKILL.md skills/<name>/references/*.md   # word and line budgets
uv run --with pyyaml python -c "import sys, yaml; print(yaml.safe_load(sys.stdin.read().split('---')[1]))" < skills/<name>/SKILL.md
```

The third command prints the parsed frontmatter, or the YAML error. Then confirm by reading: only allowed keys, every fence with a language tag, every path named in prose exists, every `references/*.md` linked from `SKILL.md`, `agents/openai.yaml` present.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Description that summarizes the workflow | Triggers first, then keywords, no steps | Agents take the summary as the instruction and never open the body |
| "Never X" for a house default | "The house default is X; use Y when Z" | Hosts obey the ban even when the documented exception applies |
| Same rule explained in two skills "for convenience" | One owner, one sentence elsewhere naming the owner | Two phrasings drift; literal models reconcile them at a cost |
| Example with an undefined helper or `...` parameters | Define it, import it, or name the owning skill | The agent copies the example verbatim |

## Gotchas

- Frontmatter that fails to parse still loads in Claude Code with an empty description, so the skill silently stops routing; `claude plugin validate .` does not catch it, hence the parse command above.
- A colon plus space inside an unquoted description (`ty: ignore`) is a YAML mapping and breaks the frontmatter; drop the colon or quote the value.
- Adding a skill means auditing every sibling's `**Related**` line and `README.md`; nothing else finds it.
- Changing `python-code-style` changes what every domain skill may omit; review the siblings after.
- `references/*.md` files are never auto-loaded; `SKILL.md` must link them by path with a one-line "load when …" pointer.
- The BoilerplateBuilder template is the reference implementation for layout and tooling; when it and a skill disagree, fix the one that is wrong and note it in the diff.
- This skill follows its own rules; after editing it, check the diff against its own tables.
