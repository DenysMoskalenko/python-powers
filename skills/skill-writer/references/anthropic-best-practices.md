# Upstream Skill-Authoring Guidance and House Deviations

Facts from the Agent Skills specification, Anthropic's skill best-practices page, the Claude Code skills reference, and the Codex and Cursor skill docs, as checked on 2026-09-05. Load this when deciding what is a hard limit versus a house choice. Sources: https://agentskills.io/specification, https://agentskills.io/skill-creation/best-practices, https://agentskills.io/skill-creation/optimizing-descriptions, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices, https://code.claude.com/docs/en/skills, https://learn.chatgpt.com/docs/build-skills, https://cursor.com/docs/skills.

## Limits every host enforces or assumes

| Item | Upstream | House |
|---|---|---|
| `name` | 1–64 chars, `a-z0-9-`, equals the folder name, no `claude`/`anthropic` | same |
| `description` | required, ≤1,024 chars, no XML tags in `name` or `description` (claude.ai uploads reject them); Claude Code lists `description` + `when_to_use` truncated at 1,536 chars; Codex loads name + description under 2% of context or 8,000 chars total | 30–60 words, ≤400 chars, triggers first, then keywords, file names and error strings; no `<` or `>` anywhere in the frontmatter |
| `SKILL.md` size | under 500 lines; 5,000 words (guide) or 5,000 tokens (spec); body loaded on activation | 300 lines and 2,000 words (`wc -w`) |
| References | `references/` (also `scripts/`, `assets/`), one level deep, linked by relative path, loaded on demand; contents list when long; no `README.md` inside the skill folder | `references/<topic>.md`, contents list above 100 lines, same budgets as `SKILL.md` |
| Spec frontmatter | `name`, `description`, optional `license`, `compatibility`, `metadata`, experimental `allowed-tools` | plus `disable-model-invocation`, `paths`, `when_to_use` (Claude Code / Cursor); `> Requires` in the body instead of `compatibility` |
| Host-only keys | Claude Code also honours `argument-hint`, `context`, `agent`, `model`, `effort`, `hooks`; claude.ai uploads reject unknown keys; Codex ignores them and reads `agents/openai.yaml` | not used |

## Principles the house rules implement

- "Claude is already very smart": include only what the agent would get wrong without it; ask per paragraph whether it justifies its token cost.
- Degrees of freedom: heuristics where many approaches are valid; a template or example where one pattern is preferred; exact commands only for fragile sequences.
- Description: what the skill does and when to use it, third person, concrete keywords, intent rather than implementation; agents consult skills only for tasks they cannot easily do alone, so one-step prompts may not trigger even a perfect description.
- Gotchas are the highest-value content: concrete corrections to mistakes the agent actually made, kept in `SKILL.md`; add one each time an agent gets something wrong.
- Tone: explain why instead of heavy-handed "MUST"; capitalized ALWAYS/NEVER is a warning sign; escalate wording only after an eval shows the calm sentence being skipped.
- Time-sensitive facts age badly; use capability language and keep versions in one place.
- One term per concept throughout a skill.
- Evals first: descriptions tuned with should-load and near-miss should-not-load prompts (Creating a skill step 4), several runs each, on every model the team uses.
- `claude plugin validate <dir>` validates only `.claude-plugin/marketplace.json`; a `SKILL.md` with unparsable frontmatter still loads, with an empty description, so parse frontmatter separately.

## Host behaviour worth knowing

- `disable-model-invocation: true` removes the skill from Claude Code's listing, so the model cannot invoke it and `/name` is unreliable; Cursor hides plugin-delivered skills with the flag from its palette; Codex ignores the key and uses `policy.allow_implicit_invocation: false` in `agents/openai.yaml`.
- `paths:` globs restrict auto-loading to work on matching files (Claude Code, Cursor); Codex has no equivalent.
- Claude Code drops the descriptions of the least-invoked skills first when the listing exceeds about 1% of the context window; `/skill-doctor` reports per-skill cost and never-invoked skills.
- Codex reads `AGENTS.md` root-to-leaf under 32 KiB; Claude Code reads `CLAUDE.md` (this repo symlinks it to `AGENTS.md`).
