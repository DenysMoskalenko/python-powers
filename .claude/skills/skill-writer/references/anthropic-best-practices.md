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

Keep `SKILL.md` as the trigger, workflow, and navigation surface. Move bulky material to `references/` when a section exceeds 200 lines, is used only in some tasks, or is mostly examples/API detail.

Rules:

- Link every reference file directly from `SKILL.md`; nested references are easy to miss.
- Keep each reference topic cohesive: providers, testing, migrations, examples, policies.
- Do not duplicate the same rule in `SKILL.md` and `references/`; pick one source of truth.
- For reference files over 100 lines, add a contents list near the top.

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

For skill changes, use the local RED-GREEN-REFACTOR loop in `SKILL.md`: capture the failure first, minimal rule change, then re-check the budgets and run the checks before handing off.

## File hygiene

- Do not add README, changelog, install guide, or extra meta-docs inside a skill.
- Use scripts only for deterministic repeatable operations.
- Use assets only when the skill consumes them to produce output.
- Keep examples complete enough to adapt, but do not provide the same example in multiple languages.
