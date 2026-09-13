---
name: skill-writer
description: Use when creating, editing, splitting, or reviewing a skill under this repository's `skills/` folder, or adding eval cases for one — folder layout, frontmatter, body skeleton, ownership boundaries, tone for current models, copy-ready examples, and the eval loop. Explicit-only; other skill systems have their own authoring guides.
disable-model-invocation: true
---

# Skill Writer (This Repository Only)

Meta-skill for authoring skills in this repository's `skills/` folder; it records the decisions the existing skills follow so edits reproduce the same shape. Other skill systems have their own authoring guides. It is explicit-only (`disable-model-invocation: true`); `AGENTS.md` step 6 tells agents to read it before touching a skill.

**Related**: none; the ownership table below names the domain skills.

Load `references/anthropic-best-practices.md` for the upstream limits behind a rule below, and `evals/scenarios.md` (repository root) when writing eval cases.

## Who reads a skill, and what that changes

Skills are loaded by current frontier coding agents in Claude Code, Codex and Cursor, and the rules below follow from how they read:

- Literally, without generalizing scope: say "every `relationship()` in `app/infrastructure/db/models/`", not "relationships".
- Over-complying with emphasis: where you would write "CRITICAL: you MUST", write "Use X when Y", with the why in the same sentence.
- Reconciling contradictions at a cost: one owner per rule.
- Already knowing the libraries: a paragraph earns its tokens only if the agent would get it wrong without it — a house decision, a fragile sequence, a gotcha.

## House style

### Folder layout

```text
skills/<skill-name>/
  SKILL.md               # required; loaded when the skill triggers
  references/<topic>.md  # optional; loaded only when SKILL.md points at it by path
  agents/openai.yaml     # required; Codex display metadata (interface.display_name, interface.short_description)
evals/                   # repo-level scenarios, runnable cases, runner, and static checker (see Evals)
```

Skill name: lowercase, hyphens, matches the folder. No `README.md` inside a skill folder; human documentation is the repository `README.md`.

### Frontmatter

```yaml
---
name: <kebab-case-name>
description: Use when <trigger 1>, <trigger 2>, or <trigger 3> — <concrete keywords users type>. [Optional] For <adjacent topic> see `<sibling-skill>`.
---
```

- `description`: 30–60 words, under 400 characters; triggers first, then keywords, file names and pasted-error strings an agent would search for; third person; no workflow steps; no `<` or `>` anywhere in the frontmatter (claude.ai uploads reject them). A sibling pointer only when a real prompt could land on the wrong skill.
- Allowed keys: `name`, `description`, `disable-model-invocation`, `paths`, `when_to_use`, `metadata` (plus the spec's `license`/`compatibility`, which hosts accept but ignore). `> Requires …` stays in the body, which all three hosts show at use time.
- `disable-model-invocation: true` removes the skill from the host's listing (Claude Code and Cursor); Codex needs `policy.allow_implicit_invocation: false` in `agents/openai.yaml`. Reference such a skill by file path.

### Body skeleton

```markdown
# <Title>

<One paragraph: what this skill owns, in 1–3 sentences.> An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires <python version>, <key libraries>.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `<skill1>`, `<skill2>`.

## <domain sections>        <!-- at least two; one excellent example per pattern -->

## Common mistakes          <!-- recommended; only mistakes the body does not already state -->

| Mistake | Do instead | Why |
|---|---|---|

## Gotchas                  <!-- required; the highest-value section -->
```

No `## When to use` section: the host routes on the description alone, so triggers in the body are paid on every load; extra sub-triggers go into `when_to_use`.

### Rule classes and tone

- **Invariant** (breaks the architecture if violated): state plainly. "Services raise domain exceptions; handlers translate them to HTTP."
- **House default** (valid alternatives exist): say so and name the escape hatch in the same sentence. "The house default is `selectinload` for collections; use `joinedload` for a to-one on a single-object fetch."
- **Heuristic** (needs measurement): give the signal. "Profile before switching loaders on a hot endpoint."

Write in plain imperatives: no capitalized emphasis, no "STOP", no "never … no exceptions" unless the exception really does not exist. Prefer "do X" over "don't do Y". No generic exhortations ("be thorough", "double-check"); current models over-apply them. A concrete procedure with a named artefact ("read the enclosing function and its call sites") is fine.

### Budgets

| File | Budget (`evals/check_skills.py` fails above it) | Upstream limit |
|---|---|---|
| `SKILL.md` | 300 lines, 1,800 words (~2.5k tokens) | 500 lines, 5,000 words |
| `references/<topic>.md` | same; one cohesive topic; contents list above 100 lines | one level deep |

The word budget is the one that bites: 300 lines of 700-character paragraphs cost twice what the line count suggests. Move a cohesive block (setup, fixtures, providers) to `references/` when `SKILL.md` passes a budget. State each rule once: a `## Common mistakes` row restating a body paragraph, or a sibling's rule re-explained "for convenience", is how a skill doubles in size without saying more.

### Code examples

- Every fence has a language tag. One excellent example per pattern.
- Copy-ready: every symbol is defined in the skill, imported from a named module, or noted as a sibling's. No `...` in parameter lists, no narrating comments.
- Verified: examples come from a scratch project generated from the BoilerplateBuilder template that passes its quality gate on current library versions; no unrun code.
- Neutral: no provider model ids, dates, version numbers, or measurement anecdotes in prose; versions live once in `> Requires`.

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
4. Add a `## <skill-name>` section to `evals/scenarios.md` and the cases to `evals/cases.json`: 3–5 should-load prompts (casual phrasing, pasted errors, file names), 2–3 near-miss should-not-load prompts naming the owning sibling, 2–4 behaviour cases whose graders check code, not prose.
5. Add the skill to every sibling's `**Related**` line where it composes, to `README.md`, and to the manifests' keywords if it widens the plugin's scope.
6. `git add skills/<name>/` and any other file you created; leave modified files unstaged and do not commit.

### Editing a skill

1. Read the whole section you are changing, including the neighbouring example; if the quoted line is already right in context, say so and change nothing.
2. If the change widens scope, re-check the ownership table; the right edit may be in a sibling.
3. Make the smallest change that fixes the observed problem; add a rule only after a repeated failure, with the eval case that would have caught it.
4. Re-run the checks below. Run the touched skill's eval cases when the owner asks (they spend API calls); otherwise list the case names.
5. `git add` any file you created; leave modified files unstaged.

### Checks before handing off

```bash
claude plugin validate .                              # .claude-plugin/marketplace.json only
uv run evals/check_skills.py                          # frontmatter, budgets, links, fences, manifests
python3 evals/run_evals.py --only <case-name> ...     # trigger + behaviour cases for the touched skill; spends API calls
```

Re-read the changed section and confirm every path named in prose exists; the checker covers links and `references/` mentions only. Bump `version` in the plugin manifests when a release changes skills.

## Evals

- `evals/cases.json` is the runnable suite: trigger cases with expected/forbidden skills, behaviour cases with regex graders over written files and code blocks. `evals/run_evals.py` runs each case in a fresh scratch project with and without the plugin; `evals/README.md` documents the flags. `evals/scenarios.md` is the specification the cases derive from; keep the two in sync.
- Graders check artifacts (files written, code fences), never prose: "do not create `utils.py`" in an explanation must not fail a must-not grader. Fixtures must not pre-empt the action under test.
- Run trigger cases on the model your team uses most; behaviour cases with and without the skill so the delta is visible.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Description that summarizes the workflow | Triggers first, then keywords, no steps | Agents take the summary as the instruction and never open the body |
| "Never X" for a house default | "The house default is X; use Y when Z" | Hosts obey the ban even when the documented exception applies |
| Rule added without an eval case | Add the case that fails without the rule | Otherwise the next edit removes the rule unnoticed |

## Gotchas

- Frontmatter that fails to parse still loads in Claude Code with an empty description, so the skill silently stops routing. `claude plugin validate .` checks only `.claude-plugin/marketplace.json`; `uv run evals/check_skills.py` parses every frontmatter.
- A colon plus space inside an unquoted description (`# ty: ignore`) is a YAML mapping and breaks the frontmatter; drop the colon or quote the value.
- Adding a skill means auditing every sibling's `**Related**` line and `README.md`; nothing else finds it.
- Changing `python-code-style` changes what every domain skill may omit; review the siblings after.
- `references/*.md` files are never auto-loaded; `SKILL.md` must link them by path with a one-line "load when …" pointer.
- The BoilerplateBuilder template is the reference implementation for layout and tooling; when it and a skill disagree, fix the one that is wrong and note it in the diff.
- This skill follows its own rules; after editing it, check the diff against its own tables.
