# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Static checks for skills/*/SKILL.md, their reference files, and the plugin manifests.

Run from anywhere: uv run evals/check_skills.py. Exit code 1 on any failure; lines
starting with "warning:" are advisory. No API calls.
"""

import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / 'skills'
MANIFESTS = (
    '.claude-plugin/plugin.json',
    '.claude-plugin/marketplace.json',
    '.codex-plugin/plugin.json',
    '.cursor-plugin/plugin.json',
    '.agents/plugins/marketplace.json',
)
ALLOWED_KEYS = {'name', 'description', 'disable-model-invocation', 'paths', 'when_to_use', 'metadata'}
MAX_LINES = 300
MAX_DESCRIPTION_CHARS = 400
DESCRIPTION_WORDS = range(30, 61)
MISTAKES_HEADING = '## Common mistakes'
MISTAKES_HEADER = '| Mistake | Do instead | Why |'
FRONTMATTER = re.compile(r'\A---\n(.*?)\n---\n', re.DOTALL)
FENCE = re.compile(r'^\s*```(.*)$')
LINK = re.compile(r'\]\(([^)\s]+)\)')
REFERENCE_MENTION = re.compile(r'((?:skills/[\w-]+/)?reference/[\w.-]+\.md)')


def check_frontmatter(skill: Path, text: str) -> list[str]:
    match = FRONTMATTER.match(text)
    if match is None:
        return ['frontmatter block missing']
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return [f'frontmatter is not valid YAML: {exc}']
    if not isinstance(meta, dict):
        return ['frontmatter is not a mapping']
    problems = [f'unknown frontmatter key {key!r}' for key in sorted(meta.keys() - ALLOWED_KEYS)]
    if meta.get('name') != skill.name:
        problems.append(f'name {meta.get("name")!r} does not match the folder name {skill.name!r}')
    description = meta.get('description')
    if not isinstance(description, str) or not description.strip():
        return [*problems, 'description is empty']
    if len(description) > MAX_DESCRIPTION_CHARS:
        problems.append(f'description is {len(description)} characters, limit {MAX_DESCRIPTION_CHARS}')
    words = len(description.split())
    if words not in DESCRIPTION_WORDS:
        problems.append(f'warning: description is {words} words, target {DESCRIPTION_WORDS[0]}-{DESCRIPTION_WORDS[-1]}')
    return problems


def check_markdown(path: Path, skill: Path, text: str) -> list[str]:
    """Line budget, language tag on every fence, and every relative link or reference/ mention resolving."""
    lines = text.splitlines()
    problems = [f'{len(lines)} lines, limit {MAX_LINES}'] if len(lines) > MAX_LINES else []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        fence = FENCE.match(line)
        if fence is None:
            continue
        if not in_fence and not fence.group(1).strip():
            problems.append(f'line {number}: code fence without a language tag')
        in_fence = not in_fence
    for target in LINK.findall(text):
        target_path = target.split('#')[0]
        if target_path and ':' not in target_path and not (path.parent / target_path).exists():
            problems.append(f'link target {target!r} does not exist')
    for mention in REFERENCE_MENTION.findall(text):
        base = ROOT if mention.startswith('skills/') else skill
        if not (base / mention).exists():
            problems.append(f'mentions {mention!r}, which does not exist')
    return problems


def check_mistakes_table(text: str) -> list[str]:
    lines = text.splitlines()
    if MISTAKES_HEADING not in lines:
        return []
    index = lines.index(MISTAKES_HEADING) + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    header = lines[index] if index < len(lines) else ''
    if header != MISTAKES_HEADER:
        return [f'{MISTAKES_HEADING} table header is {header!r}, expected {MISTAKES_HEADER!r}']
    return []


def check_openai_yaml(skill: Path) -> list[str]:
    path = skill / 'agents' / 'openai.yaml'
    if not path.exists():
        return ['agents/openai.yaml is missing']
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return [f'agents/openai.yaml is not valid YAML: {exc}']
    interface = data.get('interface') if isinstance(data, dict) else None
    if not isinstance(interface, dict):
        return ['agents/openai.yaml has no interface mapping']
    return [
        f'agents/openai.yaml lacks interface.{key}'
        for key in ('display_name', 'short_description')
        if not interface.get(key)
    ]


def check_skill(skill: Path) -> list[str]:
    skill_md = skill / 'SKILL.md'
    if not skill_md.exists():
        return [f'{skill.name}: SKILL.md is missing']
    text = skill_md.read_text()
    problems = [*check_frontmatter(skill, text), *check_markdown(skill_md, skill, text), *check_mistakes_table(text)]
    for reference in sorted((skill / 'reference').glob('*.md')):
        if f'reference/{reference.name}' not in text:
            problems.append(f'reference/{reference.name} is not linked from SKILL.md')
        problems.extend(
            f'reference/{reference.name}: {problem}'
            for problem in check_markdown(reference, skill, reference.read_text())
        )
    problems.extend(check_openai_yaml(skill))
    return [f'{skill.name}: {problem}' for problem in problems]


def check_manifests() -> list[str]:
    problems = []
    for name in MANIFESTS:
        try:
            data = json.loads((ROOT / name).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f'{name}: {exc}')
            continue
        skills_path = data.get('skills')
        if skills_path is not None and not (ROOT / skills_path).is_dir():
            problems.append(f'{name}: skills path {skills_path!r} does not exist')
    return problems


def main() -> int:
    skills = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    problems = [*check_manifests(), *(problem for skill in skills for problem in check_skill(skill))]
    failures = [problem for problem in problems if 'warning:' not in problem]
    report = '\n'.join(problems) or f'ok: {len(skills)} skills and {len(MANIFESTS)} manifests checked'
    print(report)  # noqa: T201
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
