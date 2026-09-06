# Skill evals

Runnable trigger and behaviour checks for the skills in `skills/`. They answer two questions: does the right skill load for a realistic prompt, and does a loaded skill change what the agent writes compared with no skill at all.

## Prerequisites

- Python 3.11+. The stock macOS `/usr/bin/python3` is older and the runner exits with a version message.
- An authenticated `claude` CLI, verified against 2.1.261. `--max-turns` is a hidden flag (absent from `claude --help`, still supported); if a CLI upgrade drops it, every run errors at once.
- Budget. A full default run is 41 arms — 15 trigger cases plus 13 behaviour cases in two arms — on the order of $20 on a frontier model, scaling with `--runs`. Per run, roughly $0.2–0.4 for a trigger case and $0.5–1.5 for a behaviour case.

## Run

```bash
python3 evals/run_evals.py                            # every case, each case's own arms
python3 evals/run_evals.py --only trig-fastapi-route  # one case
python3 evals/run_evals.py --tag trigger              # trigger cases only
python3 evals/run_evals.py --arms both --runs 3       # with/without, three repetitions
python3 evals/run_evals.py --model haiku              # cheaper model for smoke runs
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--only NAME...` | every case | run these cases; names that match nothing are printed |
| `--tag TAG...` | every case | keep cases carrying any of these tags; combined with `--only` by AND |
| `--arms` | `case` | `case` uses each case's own `arms`; `both` intersects with them, so trigger cases stay with-only; `with` / `without` force one arm |
| `--runs N` | 1 | repetitions per case and arm |
| `--model NAME` | whatever the CLI picks | `claude --model`. Pass it for any run you want to compare against another; it is recorded in every result and in `all.json` |
| `--max-turns N` | the case's `max_turns`, else 16 (trigger) / 25 (behaviour) | turn cap per run; a run that hits it is graded on what it did and reported as `WARN … hit the turn cap` |
| `--plugin-dir PATH` | this repository | plugin loaded in the `with` arm |
| `--cases PATH` | `evals/cases.json` | case file |
| `--workers N` | 4 | runs in flight at once |
| `--timeout SEC` | 1200 | per run; a timeout is recorded as an error, never as a pass |
| `--keep-workdirs` | off | keep the throwaway project copies instead of deleting them |
| `EVAL_WORK_ROOT` (env) | system temp dir | where those copies are made |

Each run starts a headless `claude -p` session in a fresh copy of `evals/fixture/` (a bare FastAPI project) at `$EVAL_WORK_ROOT/python-powers-evals/<stamp>/<case>-<arm>-<n>`, deliberately outside this repository: a `CLAUDE.md` or `AGENTS.md` in any ancestor directory is auto-loaded, and inside the repo it would brief the `without` arm with the playbook it is supposed to lack. The runner refuses to start a run whose workdir has such an ancestor, gives each copy its own `git init` and a dummy git identity, strips `CLAUDE*`/`ANTHROPIC*` environment variables other than the credentials, and deletes the copy afterwards unless `--keep-workdirs`.

Graded artefacts land in `evals/results/<stamp>/` (gitignored): per run the raw `*.stream.jsonl` transcript, the graded code, the prose and the result JSON, plus `all.json`. Exit code 1 means something failed — a `with` arm missed an expectation, or a run errored (non-zero `claude` exit, timeout, missing binary; such a run is never graded as a pass). A behaviour case that did not score higher with the skill than without it is printed as `WARN … no lift`, not failed: a model that already follows the rule scores 1.0 in both arms.

`claude plugin eval` (early access in Claude Code) covers the same ground; the cases here carry the same information so they can be ported when it becomes available.

## Case format (`cases.json`)

```json
{
  "name": "beh-domain-exception",
  "tags": ["behavior", "fastapi-service"],
  "arms": ["with", "without"],
  "cwd": "fixture",
  "max_turns": 20,
  "expect": ["fastapi-service"],
  "forbid": ["project-scaffolding"],
  "prompt": "Add GET /v1/authors/{author_id} ...",
  "must": ["NotFoundError"],
  "must_not": ["def get_author_by_id[\\s\\S]{0,400}raise HTTPException"],
  "note": "free text for maintainers; the runner ignores it"
}
```

- `arms`: `with` loads the plugin; `without` disables the `Skill` tool. Trigger cases use `["with"]`.
- `cwd`: `fixture` (default) or `empty` for greenfield prompts.
- `expect` / `forbid`: skills that must fire / must not fire in the `with` arm (names without the `python-powers:` prefix). `forbid` is graded on routing order: a forbidden skill fails the case only when it fires before the first expected skill, because an agent legitimately loads a sibling later as a helper (a database task that then writes tests loads `python-testing` too).
- `must`: regexes that may match any `Write` content, `Edit` replacement, or fenced code block from the agent's prose.
- `must_not`: regexes evaluated against each written payload on its own. They never see prose or fenced blocks, so quoting a skill's own counter-example cannot fail a case, and a proximity pattern cannot span two unrelated files.
- `note`: free text the runner ignores. Use it to record couplings, such as a pinned SHA that also lives in a skill.

Unknown keys, duplicate case names and repeated patterns are rejected when the file loads.

Add a case for every rule that exists because an agent got it wrong; keep prompts substantive and realistic (one-step questions rarely trigger any skill). `skills/skill-writer` is the one skill with no cases: it is `disable-model-invocation: true`, so it never fires on its own and a trigger case could not pass; its behaviour scenarios stay manual for now. The human-readable specification the cases derive from is `evals/scenarios.md`.
