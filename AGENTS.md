# AI Python Powers - Agent Instructions

## Repository Identity

This repository is the shared AI-assisted engineering playbook.

The main artifact is the `skills/` tree:

- `python-code-style` - Python 3.13+ architecture and style rules
- `python-tooling` - uv, ruff, ty, pytest, prek hooks, and CI patterns
- `python-testing` - FastAPI testing patterns and fixtures
- `fastapi-service` - FastAPI route, service, schema, config, and exception patterns
- `postgres-database` - SQLAlchemy, PostgreSQL, Alembic, and database test patterns
- `ai-agents` - pydantic-ai agent structure, providers, tools, routes, and tests
- `project-scaffolding` - greenfield project generation from the BoilerplateBuilder template (new services only)

The house rules for authoring those skills live in `.claude/skills/skill-writer/SKILL.md`.
It is a repo-local Claude Code skill (`/skill-writer` inside this checkout), not part of the
published plugin: every plugin manifest points at `skills/`, so nothing under `.claude/` ships.

## If You Are an AI Agent

Before changing files:

1. Inspect `README.md`, this `AGENTS.md`, and the relevant `skills/<name>/SKILL.md`.
2. Check `git status --short` and preserve existing user changes.
3. Verify the request against the full surrounding context before editing. Read the
   complete relevant section, not only the quoted line, and confirm the change is
   necessary and technically correct. If the requested change would be unnecessary or
   incorrect, explain why instead of changing the file.
4. Keep the change scoped to this repository's docs or skill content.
5. Do not invent CI, release steps, review rules, commands, or acceptance criteria that do
   not exist in this repository.
6. If you change a skill, read `.claude/skills/skill-writer/SKILL.md` first and follow its
   folder layout, frontmatter, body structure, ownership, and hand-off checks.

## What Belongs Here

Acceptable changes:

- General AI Python engineering conventions
- Skills that apply across multiple AI Python services
- Corrections that make existing skills clearer, more accurate, or less overlapping
- Reference material that supports a skill without bloating its main `SKILL.md`
- Repository docs that explain how humans and agents should use these skills

Do not add:

- App-specific conventions that belong in that app's repo
- Client-specific, team-private, or one-off workflow instructions
- New recommended tools or libraries without a clear reason they belong in the shared
  AI baseline
- Formatting-only churn across many skills
- Claims about tests, CI, review requirements, or deployment that are not present here

## Skill Editing Rules

When editing `skills/<name>/SKILL.md`:

- Use the `skill-writer` rules for frontmatter, structure, examples, and budgets.
- Keep ownership clean. Do not restate Python style rules inside framework skills, do not
  put FastAPI route rules in the database skill, and do not put pydantic-ai provider
  rules in generic testing docs.
- Prefer one excellent example over several mediocre examples.
- Preserve comments and deliberately worded warnings unless the change makes them
  irrelevant.

When adding a new skill:

- First confirm it has at least three distinct, recurring triggers.
- Prefer extending an existing skill if the topic is narrow or owned by a sibling skill.
- Add a folder at `skills/<kebab-name>/SKILL.md`; use `references/` only for supporting
  material that would otherwise make the main file too long.
- Update related-skill cross-references where they materially help discovery.
- Add `skills/<name>/agents/openai.yaml` with `interface.display_name` and
  `interface.short_description`; Codex reads it.
- Inspect the plugin manifests (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.agents/plugins/marketplace.json`)
  and update their discoverability metadata when the skill changes the plugin's advertised
  scope. Keep `skills` paths valid, update `keywords`, Cursor `tags`, summaries, and
  starter prompts only when they should help users find or understand the plugin.

## Validation

This repo is mostly Markdown skill content.

For every change:

- Re-read the complete changed section after editing.
- Verify links and local paths you touched exist.
- When touching a `SKILL.md` or a reference file, run the checks `skill-writer` lists
  before handing off (frontmatter parses, fences tagged, paths exist, budgets).
- Run `claude plugin validate .` when touching a manifest; it validates
  `.claude-plugin/marketplace.json` and the `plugin.json` it lists, not the Codex
  or Cursor manifests.
- Report exactly what you changed and what you verified.

For Python examples inside skills:

- Keep examples compatible with Python 3.13+.
- Follow the local `python-code-style` skill.
- Prefer examples that are realistic enough to copy into a service with minimal edits.

## Pull Request Discipline

This repository is hosted on GitHub. Say "pull request" unless you are explicitly
talking about another platform.

Before opening or preparing a pull request:

1. Confirm the problem is real and belongs in this shared skills repo.
2. Search existing issues and pull requests if GitHub access is available.
3. Show the complete diff to the repository owner.
4. Get explicit approval before submitting.
5. Include what changed, why it changed, and how it was verified.
6. If it changes anything under `skills/`, bump `version` in the same pull request, in all
   four manifests (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
   `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`): Claude Code serves the
   cached plugin until the version string changes, so without a bump auto-update never
   delivers the change. Patch for corrections, minor when a recommended pattern changes.
   After merge, the owner tags the merge commit with `claude plugin tag --push`.

Do not bundle unrelated changes.

## General Style

- Be direct and concrete.
- Keep docs terse but complete enough for another agent to follow.
- Prefer local repo conventions.
- Do not remove existing comments unless they are obsolete after the change.
- Do not touch IDE metadata such as `.idea/` unless explicitly asked.
- If an agent creates a new file, it must stage it with `git add` (only created files)
  so the file is not lost from the working tree. Do not create commits automatically;
  commits are made explicitly by the repository owner.
