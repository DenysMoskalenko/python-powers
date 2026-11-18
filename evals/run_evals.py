"""Run trigger and behaviour evals for the python-powers skills with headless Claude Code.

Each case runs in a throwaway copy of ``evals/fixture`` (or an empty directory) created *outside*
this repository, so the repo's own ``CLAUDE.md`` / ``AGENTS.md`` and git identity never leak into
the agent's context. Behaviour cases also run a "without" arm with the ``Skill`` tool disabled, and
the summary warns when the "with" arm did not score higher (both arms can legitimately reach 1.0).

Behaviour cases grade final worktree files or the arguments of a command in the final response.
Command-intent checks can also credit commands the agent attempted with the restricted Bash tool.

Usage examples::

    python3 evals/run_evals.py                             # every case, default arms
    python3 evals/run_evals.py --only trig-fastapi-route   # one case
    python3 evals/run_evals.py --tag trigger --runs 3      # all trigger cases, three runs each
    python3 evals/run_evals.py --model haiku --arms with   # cheaper model for smoke runs

The full suite requires Python 3.14+. Selections without fixture-scope checks run on 3.11+.
Model runs require an authenticated ``claude`` CLI (verified against 2.1.310).
``claude plugin eval`` is the upstream equivalent, but it reads ``case.yaml`` / ``prompt.md`` suites,
not ``cases.json``; the cases carry the same information so they can be ported.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, NamedTuple

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
FIXTURE_DIR = EVALS_DIR / 'fixture'
CODE_FENCE = re.compile(r'```[\w+-]*\n(.*?)```', re.S)
SHELL_SYNTAX = re.compile(r"""\\.|'[^']*'|"(?:\\.|[^"\\])*"|(?P<comment>(?<!\S)\#.*)|(?P<operator>[;&|]+)""")
# No Bash(cat:*): a `cat > file <<EOF` heredoc writes code the transcript grader never sees.
# Bash(uv --version): a denied version probe reads as "uv is not installed" and the agent hand-edits pyproject.toml.
ALLOWED_TOOLS = ['Skill', 'Read', 'Glob', 'Grep', 'Write', 'Edit', 'Bash(ls:*)', 'Bash(find:*)', 'Bash(uv --version)']
CASE_KEYS = frozenset(
    {
        'name', 'note', 'tags', 'arms', 'cwd', 'max_turns', 'expect', 'forbid', 'prompt', 'must', 'must_not',
        'files', 'final_command', 'must_commands', 'fixture_scopes',
    }
)
CONTEXT_FILES = ('CLAUDE.md', 'AGENTS.md')
# Every other CLAUDE*/ANTHROPIC* variable is dropped so the run does not inherit the caller's
# model, entrypoint or session overrides. These are the credentials the CLI authenticates with.
KEEP_ENV = frozenset({'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN'})
GIT_IDENTITY = {
    'GIT_AUTHOR_NAME': 'Eval Runner',
    'GIT_AUTHOR_EMAIL': 'evals@example.invalid',
    'GIT_COMMITTER_NAME': 'Eval Runner',
    'GIT_COMMITTER_EMAIL': 'evals@example.invalid',
}
SUMMARY_KEYS = (
    'case',
    'arm',
    'run',
    'skills',
    'expect_ok',
    'forbid_ok',
    'score',
    'cost',
    'turns',
    'truncated',
    'error',
)


class Transcript(NamedTuple):
    skills: list[str]
    payloads: list[str]  # one entry per Write content / Edit new_string, never concatenated
    fenced: list[str]  # fenced code blocks from prose and Bash commands; `must` reads these, `must_not` does not
    prose: str
    answer: str
    commands: list[str]
    cost: float | None
    turns: int | None
    subtype: str | None  # the result event's subtype: 'success', 'error_max_turns', ...


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', nargs='*', default=[], help='case names to run')
    parser.add_argument('--tag', nargs='*', default=[], help='run cases carrying any of these tags')
    parser.add_argument('--arms', choices=['with', 'without', 'both', 'case'], default='case')
    parser.add_argument('--runs', type=int, default=1, help='repetitions per case and arm')
    parser.add_argument('--model', default=None, help='claude --model override; pass it for comparable runs')
    parser.add_argument('--max-turns', type=int, default=None, help='override the per-case turn cap')
    parser.add_argument('--plugin-dir', default=str(REPO_ROOT), help='plugin to load in the "with" arm')
    parser.add_argument('--cases', default=str(EVALS_DIR / 'cases.json'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=int, default=1200, help='seconds before a run is killed and marked errored')
    parser.add_argument('--keep-workdirs', action='store_true', help='keep the throwaway fixture copies')
    return parser.parse_args()


def validate_pattern(name: str, key: str, pattern: str) -> None:
    if not isinstance(pattern, str) or not pattern.strip():
        raise SystemExit(f'cases.json: {name}.{key} must be a nonempty regex string')
    try:
        re.compile(pattern)
    except (re.error, OverflowError, RecursionError) as exc:
        raise SystemExit(f'cases.json: {name}.{key} has invalid regex {pattern!r}: {exc}') from exc


def validate_cases(cases: list[dict]) -> None:
    """Reject invalid case definitions before launching any paid run."""
    if not isinstance(cases, list):
        raise SystemExit('cases.json: expected a list of cases')
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise SystemExit(f'cases.json: case #{index} must be an object')
        missing = {'name', 'prompt'} - set(case)
        if missing:
            raise SystemExit(f'cases.json: case #{index} is missing {sorted(missing)}')
        for key in ('name', 'prompt'):
            if not isinstance(case[key], str) or not case[key].strip():
                raise SystemExit(f'cases.json: case #{index}.{key} must be a nonempty string')
        name, unknown = case['name'], sorted(set(case) - CASE_KEYS)
        if Path(name).name != name or name == '..' or '\x00' in name:
            raise SystemExit(f'cases.json: invalid case name {name!r}')
        if unknown:
            raise SystemExit(f'cases.json: {name} has unknown keys {unknown}; allowed: {sorted(CASE_KEYS)}')
        if name in seen:
            raise SystemExit(f'cases.json: duplicate case name {name}')
        seen.add(name)
        for key in ('tags', 'arms', 'expect', 'forbid', 'files', 'must', 'must_not', 'must_commands'):
            items = case.get(key, [])
            if not isinstance(items, list) or not all(isinstance(item, str) and item.strip() for item in items):
                raise SystemExit(f'cases.json: {name}.{key} must be a list of nonempty strings')
        if 'arms' in case:
            arms = case['arms']
            if not arms or len(set(arms)) != len(arms) or set(arms) - {'with', 'without'}:
                raise SystemExit(f'cases.json: {name}.arms must select with or without at most once each')
        if case.get('cwd', 'fixture') not in ('fixture', 'empty'):
            raise SystemExit(f'cases.json: {name}.cwd must be fixture or empty')
        if 'max_turns' in case and (type(case['max_turns']) is not int or case['max_turns'] < 1):
            raise SystemExit(f'cases.json: {name}.max_turns must be a positive integer')
        if 'files' in case:
            if not case['files']:
                raise SystemExit(f'cases.json: {name}.files must include a worktree-relative pattern')
            for pattern in case['files']:
                path = Path(pattern)
                if (
                    not path.parts or path.is_absolute() or '..' in path.parts or '\x00' in pattern
                    or any('**' in part and part != '**' for part in path.parts)
                ):
                    raise SystemExit(f'cases.json: {name}.files has invalid worktree-relative glob {pattern!r}')
        if 'fixture_scopes' in case:
            scopes = case['fixture_scopes']
            if not case.get('files') or not isinstance(scopes, dict) or not scopes:
                raise SystemExit(f'cases.json: {name}.fixture_scopes needs files and a nonempty scope-to-pattern mapping')
            for scope, pattern in scopes.items():
                if scope not in ('session', 'package', 'module', 'class', 'function'):
                    raise SystemExit(f'cases.json: {name}.fixture_scopes has unknown pytest scope {scope!r}')
                validate_pattern(name, f'fixture_scopes.{scope}', pattern)
        if 'final_command' in case:
            if 'files' in case or not case.get('must'):
                raise SystemExit(f'cases.json: {name}.final_command needs required arguments and no files')
            validate_pattern(name, 'final_command', case['final_command'])
        for key in ('must', 'must_not', 'must_commands'):
            patterns = case.get(key, [])
            if len(set(patterns)) != len(patterns):
                raise SystemExit(f'cases.json: {name} repeats a {key} pattern')
            for pattern in patterns:
                validate_pattern(name, key, pattern)


def load_cases(args: argparse.Namespace) -> list[dict]:
    cases = json.loads(Path(args.cases).read_text())
    validate_cases(cases)
    if args.only:
        unknown = sorted(set(args.only) - {case['name'] for case in cases})
        if unknown:
            print(f'no such case: {unknown}')  # noqa: T201 - CLI feedback
        cases = [case for case in cases if case['name'] in set(args.only)]
    if args.tag:
        wanted = set(args.tag)
        cases = [case for case in cases if wanted & set(case.get('tags', []))]
    if sys.version_info < (3, 14) and any('fixture_scopes' in case for case in cases):
        raise SystemExit('Selected fixture_scopes cases need Python 3.14+ to parse generated Python 3.14 source.')
    return cases


def arms_for(case: dict, args: argparse.Namespace) -> list[str]:
    case_arms = case.get('arms', ['with'])
    if args.arms == 'case':
        return case_arms
    if args.arms == 'both':  # trigger cases declare ["with"] only; a second arm would grade nothing
        return [arm for arm in ('with', 'without') if arm in case_arms] or ['with']
    return [args.arms]


def child_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(('CLAUDE', 'ANTHROPIC'))}
    env.update({key: os.environ[key] for key in KEEP_ENV if key in os.environ})
    env.update(GIT_IDENTITY)
    return env


def assert_clean_ancestry(workdir: Path) -> None:
    """A CLAUDE.md/AGENTS.md above the workdir is auto-loaded and would brief the "without" arm."""
    for directory in (workdir, *workdir.parents):
        for name in CONTEXT_FILES:
            if (directory / name).exists():
                raise SystemExit(
                    f'{directory / name} sits above the eval workdir {workdir} and would be loaded into '
                    f'the agent context. Point EVAL_WORK_ROOT at a directory with no CLAUDE.md/AGENTS.md above it.'
                )


def prepare_workdir(case: dict, arm: str, run_index: int, results_dir: Path) -> Path:
    work_root = Path(os.environ.get('EVAL_WORK_ROOT') or tempfile.gettempdir()) / 'python-powers-evals'
    workdir = work_root / results_dir.name / f'{case["name"]}-{arm}-{run_index}'
    shutil.rmtree(workdir, ignore_errors=True)
    if case.get('cwd', 'fixture') == 'empty':
        workdir.mkdir(parents=True)
    else:
        workdir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(FIXTURE_DIR, workdir)
    # A repo of its own: without it git commands would climb to whatever repo owns the temp dir.
    subprocess.run(['git', 'init', '-q'], cwd=workdir, env=child_env(), capture_output=True, check=False)  # noqa: S607 - fixed argv
    return workdir


def build_command(case: dict, arm: str, args: argparse.Namespace) -> list[str]:
    fallback = 25 if 'must' in case or 'must_not' in case else 16
    case_cap = case.get('max_turns')
    max_turns = args.max_turns if args.max_turns is not None else (fallback if case_cap is None else case_cap)
    allowed = ALLOWED_TOOLS if arm == 'with' else [tool for tool in ALLOWED_TOOLS if tool != 'Skill']
    command = [
        'claude', '-p', case['prompt'], '--output-format', 'stream-json', '--verbose',
        '--max-turns', str(max_turns), '--no-session-persistence', '--setting-sources', 'project',
        '--allowedTools', *allowed,
    ]  # fmt: skip
    if args.model:
        command += ['--model', args.model]
    if arm == 'with':
        command += ['--plugin-dir', args.plugin_dir]
    else:
        command += ['--disallowedTools', 'Skill']
    return command


def absorb(block: dict, buckets: dict[str, list[str]]) -> None:
    if block.get('type') == 'tool_use':
        name, payload = block['name'], block.get('input', {})
        if name == 'Skill':
            buckets['skills'].append(payload.get('skill') or payload.get('name') or '<unparsed>')
        elif name == 'Write':
            buckets['payloads'].append(payload.get('content', ''))
        elif name == 'Edit':
            buckets['payloads'].append(payload.get('new_string', ''))
        elif name == 'Bash':
            # A command the agent tried to run is evidence for `must` even when the harness denied
            # it (only ls/find/`uv --version` are allowed): a denied `uv add` is still the right behaviour.
            command = payload.get('command', '')
            buckets['commands'].append(command)
            buckets['fenced'].append(command)
    elif block.get('type') == 'text':
        text = block.get('text', '')
        buckets['prose'].append(text)
        buckets['fenced'].extend(CODE_FENCE.findall(text))


def collect(stdout: str) -> Transcript:
    buckets: dict[str, list[str]] = {'skills': [], 'payloads': [], 'fenced': [], 'prose': [], 'commands': []}
    cost = turns = subtype = None
    answer = ''
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') == 'assistant':
            for block in event.get('message', {}).get('content', []) or []:
                absorb(block, buckets)
        elif event.get('type') == 'result':
            cost, turns, subtype = event.get('total_cost_usd'), event.get('num_turns'), event.get('subtype')
            answer = event.get('result', '')
            buckets['prose'].append(answer)
    return Transcript(
        buckets['skills'], buckets['payloads'], buckets['fenced'], '\n'.join(buckets['prose']),
        answer, buckets['commands'], cost, turns, subtype
    )


def shell_lines(text: str) -> Iterator[list[tuple[list[str], str]]]:
    """Read simple shell commands and their following operators without executing the answer."""
    for line in text.replace('\\\n', '').splitlines():
        line = re.sub(r'^(?:[-*+] |\d+[.)] )', '', line.strip()).strip('`').removeprefix('$ ')
        segments = []
        start = 0
        for token in SHELL_SYNTAX.finditer(line):
            if token.lastgroup == 'comment':
                line = line[:token.start()]
                break
            if token.lastgroup == 'operator':
                segments.append((line[start:token.start()], token.group()))
                start = token.end()
        segments.append((line[start:], ''))
        try:
            yield [(shlex.split(command), operator) for command, operator in segments]
        except ValueError:
            continue


def final_command_args(answer: str, prefix: str) -> list[str]:
    commands = []
    for segments in shell_lines(answer):
        match segments:
            case [(['cd', _], '&&'), *rest]:
                segments = rest
        args, operator = segments[0]
        for end in range(1, len(args) + 1):
            if re.fullmatch(prefix, shlex.join(args[:end])):
                break
        else:
            continue
        options = args[end:]
        keys = [arg.split('=', 1)[0] for arg in options if '=' in arg]
        if len(set(keys)) != len(keys) or operator:
            return []
        commands.append(options)
    return commands[0] if len(commands) == 1 else []


def file_evidence(case: dict, workdir: Path) -> tuple[list[str], list[str], list[str]]:
    contents = {}
    ignored = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache'}
    for directory, subdirs, names in os.walk(workdir):
        subdirs[:] = [name for name in subdirs if name not in ignored]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(workdir)
            data = path.read_bytes()
            original = FIXTURE_DIR / relative
            if case.get('cwd') != 'empty' and original.is_file() and original.read_bytes() == data:
                continue
            if b'\0' in data:
                continue
            try:
                content = data.decode()
            except UnicodeDecodeError:
                continue
            contents[path] = f'{relative}\n{content}'

    selected = set()
    missing = []
    for pattern in case['files']:
        matches = contents.keys() & workdir.glob(pattern)
        if matches:
            selected.update(matches)
        else:
            missing.append(pattern)
    return [contents[path] for path in sorted(selected)], [contents[path] for path in sorted(contents)], missing


def fixture_source(function: ast.FunctionDef | ast.AsyncFunctionDef, definitions: dict) -> str:
    pending = [function]
    reachable = {}
    while pending:
        current = pending.pop()
        if current.name in reachable:
            continue
        reachable[current.name] = ast.unparse(current)
        for call in ast.walk(current):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in definitions:
                pending.append(definitions[call.func.id])
    return '\n'.join(reachable.values())


def check_fixture_scopes(files: list[str], patterns: dict[str, str]) -> dict[str, bool]:
    scoped: dict[str, list[str]] = {}
    checks = {}
    for file in files:
        path, _, source = file.partition('\n')
        if not path.endswith('.py'):
            continue
        try:
            module = ast.parse(source, filename=path)
        except SyntaxError as exc:
            checks[f'{path}:{exc.lineno}: {exc.msg}'] = False
            continue
        functions = {f.name: f for f in module.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for function in functions.values():
            for decorator in function.decorator_list:
                factory = decorator.func if isinstance(decorator, ast.Call) else decorator
                if ast.unparse(factory).split('.')[-1] != 'fixture':
                    continue
                keywords = decorator.keywords if isinstance(decorator, ast.Call) else []
                scope = next((kw.value for kw in keywords if kw.arg == 'scope'), ast.Constant('function'))
                if isinstance(scope, ast.Constant) and isinstance(scope.value, str):
                    scoped.setdefault(scope.value, []).append(fixture_source(function, functions))
    for scope, pattern in patterns.items():
        checks[f'{scope}-scoped fixture: {pattern}'] = any(
            re.search(pattern, source) for source in scoped.get(scope, [])
        )
    return checks


def grade(case: dict, arm: str, transcript: Transcript, workdir: Path) -> tuple[dict[str, Any], list[str]]:
    short = [skill.split(':')[-1] for skill in transcript.skills]
    missing_files = []
    match = re.search
    if 'files' in case:
        written, forbidden, missing_files = file_evidence(case, workdir)
    elif 'final_command' in case:
        written = forbidden = final_command_args(transcript.answer, case['final_command'])
        match = re.fullmatch
    else:
        written, forbidden = transcript.payloads + transcript.fenced, transcript.payloads
    # Routing is graded on order: a forbidden skill may load later as a helper (a database task that then
    # writes tests loads python-testing too), but it must not be what the prompt routed to first.
    expected_at = [short.index(name) for name in case.get('expect', []) if name in short]
    routed_before = short[: min(expected_at)] if expected_at else short
    result: dict[str, Any] = {
        'expect_ok': all(name in short for name in case.get('expect', [])) if arm == 'with' else None,
        'forbid_ok': not any(name in routed_before for name in case.get('forbid', [])) if arm == 'with' else None,
        'truncated': transcript.subtype == 'error_max_turns',
        'must': {p: any(match(p, part) for part in written) for p in case.get('must', [])},
        'must_not': {p: not any(match(p, part) for part in forbidden) for p in case.get('must_not', [])},
        'missing_files': missing_files,
    }
    if case.get('fixture_scopes'):
        result['must'].update(check_fixture_scopes(written, case['fixture_scopes']))
    evidence = forbidden if 'files' in case else written
    if case.get('must_commands'):
        commands = [
            shlex.join(words)
            for text in [*transcript.commands, transcript.answer]
            for segments in shell_lines(text)
            for words, _ in segments if words
        ]
        result['must'].update({p: any(re.match(p, cmd) for cmd in commands) for p in case['must_commands']})
        evidence = evidence + commands
    graded = list(result['must'].values()) + list(result['must_not'].values()) + [False] * len(missing_files)
    result['score'] = round(sum(graded) / len(graded), 2) if graded else None
    return result, evidence


def write_artefacts(
    results_dir: Path, prefix: str, stdout: str, transcript: Transcript, result: dict, evidence: list[str]
) -> None:
    (results_dir / f'{prefix}.stream.jsonl').write_text(stdout)
    (results_dir / f'{prefix}.code.txt').write_text('\n'.join(evidence))
    (results_dir / f'{prefix}.prose.txt').write_text(transcript.prose)
    (results_dir / f'{prefix}.json').write_text(json.dumps(result, indent=1))


def run_one(case: dict, arm: str, run_index: int, args: argparse.Namespace, results_dir: Path) -> dict:
    workdir = prepare_workdir(case, arm, run_index, results_dir)
    assert_clean_ancestry(workdir)
    command = build_command(case, arm, args)
    started = time.time()
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command, cwd=workdir, env=child_env(), capture_output=True, text=True, timeout=args.timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # missing binary, or the run ran out of time
        partial = getattr(exc, 'stdout', '') or ''
        if isinstance(partial, bytes):
            partial = partial.decode(errors='replace')
        reason = f'timed out after {args.timeout}s' if isinstance(exc, subprocess.TimeoutExpired) else repr(exc)
        completed = subprocess.CompletedProcess(command, returncode=-1, stdout=partial, stderr=reason)
    transcript = collect(completed.stdout)
    grading, evidence = grade(case, arm, transcript, workdir)
    result = {
        'case': case['name'], 'arm': arm, 'run': run_index, 'model': args.model or 'default',
        'skills': transcript.skills, 'cost': transcript.cost, 'turns': transcript.turns,
        'seconds': round(time.time() - started), 'returncode': completed.returncode,
        'error': run_error(completed.returncode, transcript), 'stderr': completed.stderr[-400:],
        **grading,
    }  # fmt: skip
    write_artefacts(results_dir, f'{case["name"]}.{arm}.{run_index}', completed.stdout, transcript, result, evidence)
    if not args.keep_workdirs:
        shutil.rmtree(workdir, ignore_errors=True)
    print(json.dumps({key: result[key] for key in SUMMARY_KEYS}), flush=True)  # noqa: T201 - CLI progress
    return result


def run_error(returncode: int, transcript: Transcript) -> str | None:
    """A run that died is never graded as a pass. A run that hit the turn cap is graded on what it did
    before the cap and reported as truncated: the skill calls it made are real, and a behaviour case that
    still scores 1.0 after truncation is noted in the summary rather than failed."""
    if returncode < 0 or (returncode != 0 and transcript.subtype != 'error_max_turns'):
        return f'claude exited {returncode}'
    if transcript.turns is None:
        return 'transcript has no result event'
    return None


def collect_failures(results: list[dict]) -> list[str]:
    failures = []
    for result in results:
        name, arm, run = result['case'], result['arm'], result['run']
        if result['error']:
            failures.append(f'{name} [{arm} run {run}]: {result["error"]}; stderr: {result["stderr"].strip()[-200:]}')
            continue
        if arm != 'with':
            continue
        broken = [p for p, ok in result['must'].items() if not ok]
        broken += [f'not {p}' for p, ok in result['must_not'].items() if not ok]
        broken += [f'missing file: {pattern}' for pattern in result.get('missing_files', [])]
        if result['expect_ok'] is False or result['forbid_ok'] is False or broken:
            failures.append(f'{name} [with run {run}]: skills={result["skills"]} patterns={broken}')
    return failures


def collect_no_lift(results: list[dict]) -> list[str]:
    """Warnings: runs that hit the turn cap, and behaviour cases whose with-arm did not beat the without-arm.
    Not failures: a model that already follows the rule scores 1.0 in both arms, and that is not a defect
    of the skill."""
    baselines = {(result['case'], result['run']): result for result in results if result['arm'] == 'without'}
    warnings = [
        f'{r["case"]} [{r["arm"]} run {r["run"]}]: hit the turn cap at {r["turns"]} turns; graded on what it did before'
        for r in results
        if r.get('truncated')
    ]
    for result in results:
        baseline = baselines.get((result['case'], result['run']))
        if result['arm'] != 'with' or result['error'] or baseline is None or baseline['error']:
            continue
        with_score, base_score = result['score'], baseline['score']
        if with_score is not None and base_score is not None and with_score <= base_score:
            warnings.append(
                f'{result["case"]} [run {result["run"]}]: no lift over the no-skill arm, '
                f'with={with_score} without={base_score}'
            )
    return warnings


def main() -> int:
    if sys.version_info < (3, 11):  # noqa: UP036 - the guard exists for older stock pythons
        raise SystemExit(f'evals/run_evals.py needs Python 3.11+, found {sys.version.split()[0]}')
    args = parse_args()
    cases = load_cases(args)
    if not cases:
        print('no cases selected')  # noqa: T201 - CLI feedback
        return 2
    results_dir = EVALS_DIR / 'results' / time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    results_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(case, arm, index) for case in cases for arm in arms_for(case, args) for index in range(args.runs)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, case, arm, index, args, results_dir) for case, arm, index in jobs]
        results = [future.result() for future in futures]
    model = args.model or 'default'
    (results_dir / 'all.json').write_text(json.dumps({'model': model, 'runs': results}, indent=1))

    failures = collect_failures(results)
    no_lift = collect_no_lift(results)
    total_cost = round(sum(result['cost'] or 0 for result in results), 2)
    print(f'\n{len(results)} runs on model {model}, ${total_cost}, results in {results_dir}')  # noqa: T201 - CLI output
    for line in no_lift:
        print(f'WARN {line}')  # noqa: T201 - CLI output
    for line in failures:
        print(f'FAIL {line}')  # noqa: T201 - CLI output
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
