"""Run with `python -m tools.work_guard --help` from the BKE checkout."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import core
from .github import GitHub
from .service import Guard


def load(path: str) -> dict:
    raw = Path(path).read_text(encoding='utf-8')
    core.need(len(raw.encode()) <= 8_000_000, 'INPUT_TOO_LARGE')
    obj = json.loads(raw, object_pairs_hook=core._unique)
    core.need(isinstance(obj, dict), 'JSON_OBJECT_REQUIRED')
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description='TORI work reservation guard; no background service.')
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect', help='read-only live snapshot + inventory id; no reservation')
    inspect.add_argument('--repo', required=True)
    plan = sub.add_parser('plan', help='offline plan for an existing connected GitHub tool; DOES NOT reserve')
    plan.add_argument('--snapshot', required=True)
    plan.add_argument('--request', required=True)
    check = sub.add_parser('check', help='read-only check of a previously acquired write operation')
    check.add_argument('--snapshot', required=True)
    check.add_argument('--request', required=True)
    apply = sub.add_parser('apply', help='explicit live mutation; GH_TOKEN or GITHUB_TOKEN in environment')
    apply.add_argument('--repo', required=True)
    apply.add_argument('--request', required=True)
    apply.add_argument('--yes', action='store_true', help='authorize only this request')
    args = parser.parse_args()
    try:
        if args.command in {'plan', 'check'}:
            s, q = load(args.snapshot), load(args.request)
            # `inspect` output can be used directly without deleting the summary wrapper.
            s = s.get('snapshot', s)
            if args.command == 'check':
                result = core.check(s, q)
            else:
                result = core.accept(s, q) if q['action'] == 'accept' else core.plan(s, q)
                result['dry_run'] = True
                if result['mutation']:
                    result['connector_write'] = dict(repository_full_name=s['repo'], path=core.REGISTRY,
                        branch='main', sha=s['registry_sha'], content=result['document'],
                        message='chore(coordination): work checkpoint [skip ci] [skip render]')
                    result['next'] = 'Use create_file if sha is null, otherwise update_file. Confirm receipt before effects.'
        elif args.command == 'inspect':
            result = Guard(GitHub(args.repo)).inspect()
        else:
            core.need(args.yes, 'EXPLICIT_APPLY_REQUIRED')
            q = load(args.request)
            guard = Guard(GitHub(args.repo))
            if q['action'] == 'create-branch':
                result = guard.create_branch(q)
            elif q['action'] == 'write':
                result = guard.write(q, q['files'], q['message'])
            elif q['action'] == 'sync':
                result = guard.sync(q)
            elif q['action'] == 'merge':
                result = guard.merge(q)
            else:
                result = guard.transition(q)
            # Do not echo source code, transport credentials, or a whole private registry on mutations.
            result = dict(applied=result['mutation'], replay=result.get('replay', False),
                          receipt=result['receipt'], task=q.get('task'))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except core.Refused as exc:
        print(json.dumps({'ok': False, 'error': exc.code}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, OSError):
        print('{"ok": false, "error": "INVALID_INPUT_OR_ADAPTER_RESPONSE"}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
