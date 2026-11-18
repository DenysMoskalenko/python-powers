import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
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
        command = (
            f"{CASES[name]['final_command']} --no-input project_type=fastapi_db project_name=order-service "
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

    def test_partial_stream_timeout_still_writes_the_suite_summary(self) -> None:
        cases = self.work / 'cases.json'
        cases.write_text(json.dumps([{'name': 'timeout', 'prompt': 'offline fixture'}]))
        args = argparse.Namespace(
            cases=str(cases), only=[], tag=[], arms='case', runs=1, keep_workdirs=False,
            workers=1, timeout=0.5, model=None,
        )
        command = [
            sys.executable, '-u', '-c',
            'import time; print(\'{"type":"system"}\'); time.sleep(5)',
        ]
        with (
            patch.object(runner, 'EVALS_DIR', self.work),
            patch.object(runner, 'parse_args', return_value=args),
            patch.object(runner, 'build_command', return_value=command),
            patch.dict('os.environ', EVAL_WORK_ROOT=str(self.work)),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(runner.main(), 1)
        summary, = (self.work / 'results').glob('*/all.json')
        result, = json.loads(summary.read_text())['runs']
        self.assertIn('timed out', result['stderr'])
        self.assertTrue(result['error'])
        stream = summary.parent / 'timeout.with.0.stream.jsonl'
        self.assertEqual(json.loads(stream.read_text()), {'type': 'system'})
