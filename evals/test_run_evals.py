import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_evals as runner


CASES = {case['name']: case for case in json.loads((runner.EVALS_DIR / 'cases.json').read_text())}


class TestGrader(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def grade(self, name: str, answer: str = '', attempts: list[dict] | None = None) -> dict:
        case = CASES[name]
        skill = {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': case['expect'][0]}}
        events = [
            {'type': 'assistant', 'message': {'content': [skill, *(attempts or [])]}},
            {'type': 'result', 'subtype': 'success', 'num_turns': 1, 'result': answer},
        ]
        transcript = runner.collect('\n'.join(json.dumps(event) for event in events))
        result, _ = runner.grade(case, 'with', transcript, self.work)
        return result

    def test_scaffold_checks_only_the_final_command(self) -> None:
        name = 'beh-scaffold-command'
        template = 'https://github.com/DenysMoskalenko/BoilerplateBuilder'
        command = (
            f'uv tool run cookiecutter {template} --no-input project_type=fastapi_db project_name=order-service '
            "project_description='Order service' author_name=Ada author_email=ada@example.com "
            'python_version=3.14 use_otel_observability=yes generate_local_otel_stack=yes '
            'use_github_actions=yes initialize_git=yes extract_to_current_dir="Create New"'
        )
        answer = '```bash\n' + command.replace(' project_type', ' \\\n project_type') + '\n```\n'
        self.assertEqual(self.grade(name, answer + 'Omit `use_pre_commit=yes`.')['score'], 1)
        self.assertLess(self.grade(name, answer.replace(' --no-input', ' use_pre_commit=yes --no-input'))['score'], 1)
        self.assertLess(self.grade(name, 'Done.', [{'type': 'text', 'text': answer}])['score'], 1)
        self.assertLess(self.grade(name, command.replace('python_version=3.14', 'python_version=3.13'))['score'], 1)
        self.assertLess(self.grade(name, command + ' python_version=3.13')['score'], 1)
        for prefix in (
            f'cd ~/src && uvx cookiecutter {template}.git',
            'uv tool run cookiecutter gh:DenysMoskalenko/BoilerplateBuilder',
        ):
            with self.subTest(prefix=prefix):
                alternative = command.replace(f'uv tool run cookiecutter {template}', prefix)
                self.assertEqual(self.grade(name, alternative)['score'], 1)
        for invalid in (
            command.replace(template, template + '-fork'), f'echo "{command}"', command + ' && echo done',
            command + '\n' + command,
        ):
            with self.subTest(command=invalid):
                self.assertLess(self.grade(name, invalid)['score'], 1)

    def test_tooling_commands_in_answer_or_attempted_script(self) -> None:
        name = 'beh-tooling'
        requirement, = CASES[name]['must_commands']
        command = 'uv add python-json-logger'
        self.assertTrue(self.grade(name, f'cd . && {command}')['must'][requirement])
        attempt = {'type': 'tool_use', 'name': 'Bash', 'input': {'command': f'pwd\n{command}'}}
        self.assertTrue(self.grade(name, attempts=[attempt])['must'][requirement])
        for valid in (f'- `{command}`', f'1. `{command}`', 'uv add --project . python-json-logger'):
            with self.subTest(valid=valid):
                self.assertTrue(self.grade(name, valid)['must'][requirement])
        for invalid in (
            f'echo "{command}"', f"printf '%s ' '&&' {command}", command + '-extra', command + ' --dev',
            'uv add --group test python-json-logger', command + ' --optional=testing',
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(self.grade(name, invalid)['must'][requirement])

    def test_forbidden_patterns_cover_final_files_outside_required_globs(self) -> None:
        name = 'beh-tooling'
        target = self.work / 'pyproject.toml'
        target.write_text('[project]\nname = "example"')
        extra = self.work / 'setup.sh'
        extra.write_text('pip install python-json-logger\n')
        self.assertFalse(self.grade(name)['must_not']['pip install'])
        attempt = {'type': 'tool_use', 'name': 'Write', 'input': {'content': extra.read_text()}}
        extra.write_text('uv add python-json-logger\n')
        (self.work / '.venv').mkdir()
        (self.work / '.venv' / 'installed.py').write_text('pip install')
        (self.work / 'data.bin').write_bytes(b'pip install\0')
        self.assertTrue(self.grade(name, attempts=[attempt])['must_not']['pip install'])

    def test_postgres_fixtures_must_exist_at_the_requested_path(self) -> None:
        name = 'beh-testcontainers-import'
        reference = runner.REPO_ROOT / 'skills/postgres-database/references/testing.md'
        source = '\n'.join(runner.CODE_FENCE.findall(reference.read_text()))
        attempts = [{'type': 'tool_use', 'name': 'Write', 'input': {'content': source}}]
        self.assertLess(self.grade(name, f'```python\n{source}\n```', attempts)['score'], 1)
        tests = self.work / 'tests'
        tests.mkdir()
        (tests / 'helpers.py').write_text(source)
        self.assertLess(self.grade(name, attempts=attempts)['score'], 1)
        target = tests / 'conftest.py'
        target.write_text(source)
        self.assertEqual(self.grade(name)['score'], 1)
        target.write_text(source.replace('await trans.rollback()', 'pass'))
        self.assertLess(self.grade(name, attempts=attempts)['score'], 1)
        target.write_text(source.replace("scope='function'", "loop_scope='session'"))
        self.assertEqual(self.grade(name)['score'], 1)
        swapped = source.replace("scope='session'", "scope='TEMP'").replace("scope='function'", "scope='session'")
        target.write_text(swapped.replace("scope='TEMP'", "scope='function'"))
        self.assertLess(self.grade(name)['score'], 1)
        target.write_text(
            source.replace('await trans.rollback()', 'await release(trans)')
            + '\nasync def release(transaction):\n    await transaction.rollback()\n'
        )
        self.assertEqual(self.grade(name)['score'], 1)
        target.write_text(source + '\nif False:\n    from testcontainers.postgres import PostgresContainer\n')
        self.assertFalse(all(self.grade(name)['must_not'].values()))
        target.write_text('def broken(:\n')
        self.assertTrue(any('tests/conftest.py:1:' in key for key in self.grade(name)['must']))

    @unittest.skipUnless(sys.version_info >= (3, 14), 'requires Python 3.14 syntax')
    def test_fixtures_allow_python_314_syntax(self) -> None:
        target = self.work / 'tests' / 'conftest.py'
        target.parent.mkdir()
        reference = runner.REPO_ROOT / 'skills/postgres-database/references/testing.md'
        source = '\n'.join(runner.CODE_FENCE.findall(reference.read_text()))
        target.write_text(source + '\ntry:\n    pass\nexcept ValueError, TypeError:\n    pass\n')
        self.assertEqual(self.grade('beh-testcontainers-import')['score'], 1)

    def test_older_runners_check_only_selected_fixture_cases(self) -> None:
        args = argparse.Namespace(cases=str(runner.EVALS_DIR / 'cases.json'), only=[], tag=[])
        with patch.object(sys, 'version_info', (3, 13)):
            with self.assertRaisesRegex(SystemExit, 'Python 3.14'):
                runner.load_cases(args)
            args.only = ['trig-fastapi-route']
            self.assertEqual([case['name'] for case in runner.load_cases(args)], args.only)

    def test_invalid_cases_fail_before_starting_any_run(self) -> None:
        cases = self.work / 'cases.json'
        args = argparse.Namespace(cases=str(cases), only=[], tag=[])
        valid = {'name': 'valid', 'prompt': 'first'}
        invalid = {'name': 'bad', 'prompt': 'second', 'must': ['expected']}
        for field, value in (
            ('must_commands', 'uv'), ('must', [None]), ('must_not', ['(']),
            ('files', '.'), ('files', ['.']), ('files', ['foo**bar']),
            ('final_command', []), ('final_command', '['),
            ('fixture_scopes', {}), ('fixture_scopes', {'session': []}), ('fixture_scopes', {'session': '('}),
        ):
            with self.subTest(field=field, value=value):
                case = {**invalid, field: value}
                if field == 'fixture_scopes':
                    case['files'] = ['test.py']
                cases.write_text(json.dumps([valid, case]))
                with patch.object(runner, 'parse_args', return_value=args), patch.object(runner, 'run_one') as run:
                    with self.assertRaisesRegex(SystemExit, 'bad'):
                        runner.main()
                    run.assert_not_called()

    def test_partial_stream_timeout_still_writes_the_suite_summary(self) -> None:
        cases = self.work / 'cases.json'
        cases.write_text(json.dumps([{'name': 'timeout', 'prompt': 'offline fixture'}]))
        args = argparse.Namespace(
            cases=str(cases), only=[], tag=[], arms='case', runs=1, keep_workdirs=False,
            workers=1, timeout=1200, model=None, max_turns=None, plugin_dir=str(runner.REPO_ROOT),
        )
        workdir = self.work / 'fixture'
        workdir.mkdir()
        timeout = subprocess.TimeoutExpired('claude', args.timeout, output=b'{"type":"system"}\n')
        with (
            patch.object(runner, 'EVALS_DIR', self.work),
            patch.object(runner, 'parse_args', return_value=args),
            patch.object(runner, 'prepare_workdir', return_value=workdir),
            patch.object(runner.subprocess, 'run', side_effect=timeout),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(runner.main(), 1)
        summary, = (self.work / 'results').glob('*/all.json')
        result, = json.loads(summary.read_text())['runs']
        self.assertIn('timed out', result['stderr'])
        self.assertTrue(result['error'])
        stream = summary.parent / 'timeout.with.0.stream.jsonl'
        self.assertEqual(json.loads(stream.read_text()), {'type': 'system'})
