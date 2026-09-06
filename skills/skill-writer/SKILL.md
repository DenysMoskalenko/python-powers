---
name: skill-writer
description: Use when creating, editing, splitting, or reviewing a skill under this repository's `skills/<name>/`, or adding eval cases for one — folder layout, frontmatter, body skeleton, ownership boundaries, tone for current models, copy-ready examples, and the eval loop. Explicit-only; other skill systems have their own authoring guides.
disable-model-invocation: true
---

# Skill Writer (This Repository Only)

Meta-skill for authoring skills in this repository's `skills/` folder. It records the decisions the existing skills follow so edits reproduce the same shape without re-deriving them. It applies only to `skills/<name>/` inside this repository; other skill systems (`~/.claude/skills`, `~/.codex/skills`, third-party plugins) have their own authoring guides.

This skill is explicit-only (`disable-model-invocation: true`), so hosts never load it on their own. `AGENTS.md` step 6 tells agents to read this file before touching a skill; that instruction is the trigger.

**Related**: none — used alone; the ownership table below names the domain skills.

Load `reference/anthropic-best-practices.md` when you need the upstream limits (name, description, size, frontmatter keys) or the host behaviour behind a rule below. Load `evals/scenarios.md` (repository root) when writing or updating eval cases.

## Who reads a skill, and what that changes

Skills are loaded by current frontier coding agents in Claude Code, Codex and Cursor. Their vendors' current prompting guides agree on the points below, and the rules in this file follow from them:

- They follow instructions literally and do not generalize scope on their own. Say "every `relationship()` in `app/infrastructure/db/models/`", not "relationships".
- They over-comply with emphatic language. Anthropic's guidance for its current models: skills written for earlier models "are often too prescriptive … and can degrade output quality"; where you would have written "CRITICAL: you MUST", write "Use X when Y".
- They reconcile contradictions at a cost (extra reasoning, or an early block on some models). Two skills must never state the same rule differently; one owner per rule.
- They already know the libraries. A paragraph earns its tokens only if the agent would get it wrong without it: a house decision, a fragile sequence, or a gotcha.
- Reasons generalize better than bans. Put the why in the same sentence as the rule when it is not obvious.

## House style

### Folder layout

```text
skills/<skill-name>/
  SKILL.md              # required; loaded when the skill triggers
  reference/<topic>.md  # optional; loaded only when SKILL.md points at it by path
  agents/openai.yaml    # required; Codex display metadata (interface.display_name, interface.short_description)
evals/                  # repo-level scenarios, runnable cases, runner, and static checker (see Evals)
```

Skill name: lowercase, hyphens, matches the folder (`python-testing`, not `tests`).

### Frontmatter

```yaml
---
name: <kebab-case-name>
description: Use when <trigger 1>, <trigger 2>, or <trigger 3> — <concrete keywords users type>. [Optional] For <adjacent topic> see `<sibling-skill>`.
---
```

- `description`: 30–60 words and under 400 characters; triggers first, then the keywords (Claude Code truncates the listing at 1,536 characters, Codex front-loads under an 8,000-character budget); third person; keywords and pasted-error strings an agent would search for; no ordered workflow steps. Add a sibling pointer only when a real prompt could plausibly land on the wrong skill ("For ruff and formatter configuration see `python-tooling`"); do not add a blanket "Does not cover …" sentence for what the name already implies.
- Allowed keys: `name`, `description`, `disable-model-invocation`, `paths`, `when_to_use`, `metadata` (plus the spec's `license`/`compatibility`, which hosts accept but ignore). Anything else is host-specific and breaks portability. `> Requires …` stays in the body because all three hosts show the body at use time.
- `disable-model-invocation: true` removes the skill from the host's listing entirely (Claude Code and Cursor); Codex needs the same intent in `agents/openai.yaml` as `policy.allow_implicit_invocation: false`. Keep the two in sync, and reference such a skill by file path in docs, not by slash command.

### Body skeleton

```markdown
# <Title>

<One paragraph: what this skill owns, in 1–3 sentences.> An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires <python version>, <key libraries>.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `<skill1>`, `<skill2>`.
[Optional one line:] For <adjacent topic> use `<sibling-skill>`.

## <domain sections>        <!-- at least two; one excellent example per pattern -->

## Common mistakes          <!-- recommended for domain and discipline skills -->

| Mistake | Do instead | Why |
|---|---|---|

## Gotchas                  <!-- required; the highest-value section -->
```

No `## When to use` section: the host routes on the description alone, so restating triggers in the body is paid on every load. Sub-triggers that do not fit the description go into `when_to_use` in the frontmatter.

### Rule classes and tone

- **Invariant** (breaks the architecture if violated): state plainly. "Services raise domain exceptions; exception handlers translate them to HTTP."
- **House default** (a choice, valid alternatives exist): say so and name the escape hatch in the same sentence. "The house default is `selectinload` for collections; use `joinedload` for a to-one on a single-object fetch."
- **Heuristic** (needs measurement): give the signal to check. "Profile before switching loaders on a hot list endpoint."

Write in plain imperatives. No capitalized emphasis, no "STOP", no "never … no exceptions" unless the exception really does not exist. Prefer "do X" over "don't do Y"; when a boundary must be negative, pair it with the positive alternative. Do not add generic exhortations about effort, thinking, or care ("be thorough", "double-check", "if in doubt use X"); current models over-apply them. A concrete procedure with a named artefact ("read the enclosing function and its call sites") is fine.

### Line budget

| File | Budget (`evals/check_skills.py` fails above it) | Upstream limit |
|---|---|---|
| `SKILL.md` | 300 lines (~5k tokens) | 500 lines |
| `reference/<topic>.md` | 300 lines; one cohesive topic; add a contents list above 100 lines | one level deep |

Move a cohesive block (setup, testing fixtures, providers) to `reference/` when `SKILL.md` passes 300 lines or the block is used only in some tasks.

### Code examples

- Every fence has a language tag. One excellent example per pattern.
- Copy-ready: every symbol is defined in the skill, imported from a named module, or noted as belonging to a sibling skill. No `...` in parameter lists. No narrating comments.
- Verified: examples come from a project that passes its quality gate — a scratch project generated from the BoilerplateBuilder template on current library versions. Do not paste unrun code.
- Neutral: no provider model ids, dates, or library version numbers in prose; versions live once in `> Requires`. Use `app/` and `app/domains/<feature>/`.

## Ownership and composition

One owner per topic. When a rule needs another skill's material to be complete, move the rule to that skill instead of linking "see `<sibling>` for the full pattern".

| Topic | Owner | Not restated in |
|---|---|---|
| Type hints, naming, DI, class layout, architecture principles, fail-fast | `python-code-style` | all others |
| uv / ruff / ty / pytest config, commands, prek hooks, CI, warnings policy | `python-tooling` | all others |
| API-level tests, factories, test helpers, dependency-override utilities, coverage policy | `python-testing` | all others |
| Routes, service shape, schemas, exception handlers, settings, app factory, module layout | `fastapi-service` | `postgres-database`, `ai-agents` |
| SQLAlchemy models, loading strategy, query/pagination/filter helpers, Alembic, DB test fixtures | `postgres-database` | `fastapi-service`, `ai-agents` |
| pydantic-ai agents, tools, model registry, provider settings, agent test fixtures | `ai-agents` | `fastapi-service`, `postgres-database` |
| Greenfield generation from the template | `project-scaffolding` | all others |

Services own their queries (that is the architecture), so `fastapi-service` shows the service shape with one lookup and `postgres-database` shows the full query patterns; the two examples must agree.

| Task | Load alongside `python-code-style` |
|---|---|
| Add CRUD endpoint with DB | `fastapi-service` + `postgres-database` |
| Add AI agent endpoint | `ai-agents` + `fastapi-service` |
| Write or update tests | `python-testing` + the domain skill(s) |
| Set up tooling / CI | `python-tooling` |
| Start a new service | `project-scaffolding`, then the domain skills |

All domain skills assume `python-code-style` is in effect and do not restate it.

## Workflow

### Creating a skill

1. List three or more distinct, recurring triggers; fewer means the content belongs in an existing skill.
2. Check the ownership table; if more than about 30% of the content belongs elsewhere, extend that skill instead.
3. Write the description, then the body from the skeleton. Verify every example in a project that passes its quality gate.
4. Add a `## <skill-name>` section to `evals/scenarios.md` and the cases to `evals/cases.json`: 3–5 should-load prompts (substantive, casual phrasing, pasted errors), 2–3 near-miss should-not-load prompts naming the owning sibling, and 2–4 behaviour cases whose graders check code, not prose.
5. Add the skill to every sibling's `**Related**` line where it composes, to `README.md`, and to the plugin manifests' keywords if it widens the plugin's scope.
6. `git add skills/<name>/` and any other file you created; leave modified files unstaged unless the owner asks. Do not commit; the owner commits.

### Editing a skill

1. Read the whole section you are changing, including table headers and the neighbouring example; if the quoted line is already right in context, say so and change nothing.
2. If the change widens scope, re-check the ownership table; the right edit may be in a sibling.
3. Make the smallest change that fixes the observed problem. Add a rule only after a repeated failure, then add the eval case that would have caught it.
4. Re-run the checks below. Run the eval cases for the touched skill when the owner asks for it (they spend API calls); otherwise list the case names to run. Adjust cases only with a stated reason in the diff.
5. `git add` any file you created; leave modified files unstaged unless the owner asks.

### Checks before handing off

```bash
claude plugin validate .                              # .claude-plugin/marketplace.json only
uv run evals/check_skills.py                          # frontmatter, budgets, links, fences, manifests
python3 evals/run_evals.py --only <case-name> ...     # trigger + behaviour cases for the touched skill; spends API calls
```

Re-read the changed section once more and confirm every path named in prose exists; the checker covers links and `reference/` mentions only.

## Evals

- `evals/cases.json` is the runnable suite (trigger cases with expected/forbidden skills; behaviour cases with regex graders over written files and code blocks). `evals/run_evals.py` runs each case in a fresh scratch project with the plugin loaded and, for behaviour cases, once more without it, and prints skills fired, score, cost, and turns. `evals/README.md` documents the format and flags.
- `evals/scenarios.md` is the human-readable specification the cases are derived from; keep the two in sync when a skill's must-produce tokens change. The runnable suite is a subset of the spec; `skill-writer` (`disable-model-invocation: true`) has no trigger cases, and its behaviour scenarios are run by hand.
- `evals/check_skills.py` is the static check (frontmatter, budgets, links, fences, `agents/openai.yaml`, manifests); it spends no API calls.
- Graders check artifacts (files written, code fences), never prose: a sentence saying "do not create `utils.py`" must not fail a must-not grader. Fixtures must not pre-empt the action under test.
- Run trigger cases on the model your team uses most; behaviour cases with and without the skill so the delta is visible.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Description that summarizes the workflow | Triggers first, then concrete keywords, no steps | Agents take the summary as the instruction and never open the body |
| `## When to use` section repeating the description | Drop it; use `when_to_use` frontmatter for extra triggers | The body is read after routing; the section costs tokens on every load |
| Same rule in two skills "for convenience" | One owner, one sentence elsewhere naming the owner | Two phrasings drift; literal models reconcile them at a cost |
| "Never X" for a house default | "The house default is X; use Y when Z" | Hosts obey the ban even when the documented exception applies |
| Capitalized emphasis, `STOP` tables, persuasion tricks | Plain imperative with the reason | Current models over-trigger on emphasis; the reason generalizes |
| Example with an undefined helper or `...` parameters | Define it, import it, or name the owning skill | The agent copies the example verbatim |
| Model ids, dates, or version numbers in prose | Capability language; versions only in `> Requires` | Ages within weeks |
| Rule added without an eval case | Add the case that fails without the rule | Otherwise the next edit removes the rule unnoticed |
| A "must not" grader that matches prose | Grade files and code fences only | Explanations legitimately mention the forbidden token |
| `SKILL.md` over 300 lines without a reference split | Move the largest cohesive block to `reference/` | Every load pays for the whole file |

## Gotchas

- Frontmatter that fails to parse still loads in Claude Code, with an empty description: the skill silently stops routing. `claude plugin validate .` checks only `.claude-plugin/marketplace.json`; `uv run evals/check_skills.py` parses every frontmatter.
- Adding a skill means auditing every sibling's `**Related**` line and `README.md`; nothing else discovers it.
- Changing `python-code-style` changes what every domain skill may omit; review the siblings after editing it.
- `reference/*.md` files are never auto-loaded; `SKILL.md` must link them by path with a one-line "load when …" pointer.
- The BoilerplateBuilder template is the reference implementation for the layout (`app/domains/<feature>/`) and the tooling baseline; when the template and a skill disagree, fix the one that is wrong and note it in the diff rather than teaching both.
- This skill follows its own rules; after editing it, re-run its Common mistakes table against the diff.
