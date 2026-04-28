# Anthropic Skill Authoring Best Practices

Adapted for this repository from upstream Superpowers and Anthropic skill-authoring guidance.

## Core principles

**Concise is key.** Assume the model is already capable. Add only repo-specific decisions, fragile procedures, or patterns the model would not reliably infer.

Before adding prose, ask:

- Does this explain a non-obvious local convention?
- Does it prevent a known failure mode?
- Does it justify its token cost every time the skill loads?

**Set the right degree of freedom.**

| Situation | Best format |
|---|---|
| Many valid approaches, context-dependent judgment | Short principles or heuristics |
| Preferred pattern with context-specific variation | Pseudocode, compact example, or checklist |
| Fragile sequence where mistakes are expensive | Exact command/script and strict ordering |

## Progressive disclosure

Keep `SKILL.md` as the trigger, workflow, and navigation surface. Move bulky material to `reference/` when it is over about 100 lines, used only in some tasks, or mostly examples/API detail.

Rules:

- Link every reference file directly from `SKILL.md`; nested references are easy to miss.
- Keep each reference topic cohesive: providers, testing, migrations, examples, policies.
- Do not duplicate the same rule in `SKILL.md` and `reference/`; pick one source of truth.
- For long reference files, add a short contents list near the top.

## Description quality

The description decides whether the skill loads. It should contain trigger conditions, not a process recipe.

Good descriptions:

- Start with `Use when...`
- Are third-person and concrete
- Include keywords an agent or user would search for
- Mention sibling skills only when confusion is plausible

Bad descriptions:

- Summarize steps from the body
- Use first person
- Add exclusions already implied by the name
- Repeat the same trigger with `Use when...` and `Apply when...`

## Workflows and validation loops

Use a workflow only when skipping or reordering steps would likely break the outcome. A good workflow has:

- Clear entry condition
- Ordered actions
- Verification step
- Failure recovery path

For skill changes, use the local RED-GREEN-REFACTOR loop in `SKILL.md`: scenario first, minimal rule change, then re-check scenarios and line budget.

## File hygiene

- Do not add README, changelog, install guide, or extra meta-docs inside a skill.
- Use scripts only for deterministic repeatable operations.
- Use assets only when the skill consumes them to produce output.
- Keep examples complete enough to adapt, but do not provide the same example in multiple languages.
