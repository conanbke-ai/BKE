"""Pure, fail-closed coordination rules. No network, subprocesses or credentials.

The managed JSON is appended to ACTIVE_WORK.md. Its enclosing prose remains
byte-for-byte intact. A plan is NOT a reservation until its CAS write succeeds.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

BEGIN = '\n\n<!-- TORI_WORK_GUARD:BEGIN -->\n```json\n'
END = '\n```\n<!-- TORI_WORK_GUARD:END -->\n'
REGISTRY = 'ACTIVE_WORK.md'
TERMINAL = {'MERGED', 'CANCELLED', 'VALIDATED'}
STATES = TERMINAL | {'HOLD', 'CLAIMED', 'BRANCHING', 'ACTIVE', 'WRITING',
                     'HANDOFF', 'BLOCKED', 'READY', 'INTEGRATING', 'SYNCING'}
HIGH_TAGS = {'AUTH', 'AUTHZ', 'SESSION', 'ACCOUNT_RECOVERY', 'PAYMENT', 'REFUND',
             'WALLET', 'WEBHOOK', 'PII', 'ADMIN', 'SECURITY', 'DESTRUCTIVE_DB'}
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z')
REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')


class Refused(Exception):
    """A stable public error code, without secrets or raw provider responses."""
    def __init__(self, code: str, detail: str = '') -> None:
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def need(condition: Any, code: str, detail: str = '') -> None:
    if not condition:
        raise Refused(code, detail)


def digest(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def identifier(value: Any) -> str:
    need(isinstance(value, str) and ID.fullmatch(value), 'BAD_IDENTIFIER')
    return value


def text(value: Any) -> str:
    need(isinstance(value, str) and 0 < len(value.strip()) <= 4000, 'TEXT_REQUIRED')
    return value


def scope(value: Any) -> str:
    """Only exact paths and terminal /** directory scopes; no glob guessing."""
    need(isinstance(value, str) and value and len(value) <= 512, 'BAD_SCOPE')
    if value == '**':
        return value
    if value.endswith('/**'):
        value = value[:-2]
    need(not value.startswith('/') and not any(c in value for c in '\\:%?#[]*\x00\n\r'),
         'BAD_SCOPE')
    parts = value.rstrip('/').split('/')
    need(all(p and p not in {'.', '..'} and not p.endswith((' ', '.')) for p in parts),
         'BAD_SCOPE')
    return value


def covers(grant: str, path: str) -> bool:
    grant, path = scope(grant).casefold(), scope(path).casefold()
    return grant == '**' or grant == path or (grant.endswith('/') and path.startswith(grant))


def intersects(a: str, b: str) -> bool:
    return covers(a, b) or covers(b, a)


def scopes(values: Any, required: bool = True) -> list[str]:
    need(isinstance(values, list) and len(values) <= 128, 'BAD_SCOPES')
    result = sorted(set(scope(v) for v in values))
    need(bool(result) or not required, 'EMPTY_SCOPE')
    return result


def branch_name(value: Any, new: bool = False) -> str:
    need(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', value),
         'BAD_BRANCH')
    need('..' not in value and not any(not p or p.startswith('.') or p.endswith(('.', '.lock'))
                                     for p in value.split('/')), 'BAD_BRANCH')
    if new:
        need(value.startswith(('work/', 'validation/')), 'BRANCH_PREFIX')
        need(not re.search(r'-(v\d+|final\d*|actual|real|new)$', value), 'DUPLICATE_STYLE_NAME')
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for k, v in pairs:
        need(k not in result, 'DUPLICATE_JSON_KEY')
        result[k] = v
    return result


def decode(document: str) -> tuple[str, dict | None]:
    need(isinstance(document, str) and len(document.encode()) <= 450_000, 'REGISTRY_TOO_LARGE')
    if 'TORI_WORK_GUARD:' not in document:
        return document, None
    need(document.count(BEGIN) == 1 and document.count(END) == 1 and document.endswith(END),
         'CORRUPT_REGISTRY')
    legacy, encoded = document.split(BEGIN)
    try:
        state = json.loads(encoded[:-len(END)], object_pairs_hook=_unique)
    except (ValueError, TypeError) as exc:
        raise Refused('CORRUPT_REGISTRY') from exc
    need(isinstance(state, dict) and state.get('schema') == 1, 'SCHEMA_UNSUPPORTED')
    need(type(state.get('revision')) is int and state['revision'] >= 0, 'CORRUPT_REGISTRY')
    need(isinstance(state.get('tasks'), dict) and isinstance(state.get('receipts'), dict),
         'CORRUPT_REGISTRY')
    need(isinstance(state.get('events'), list), 'CORRUPT_REGISTRY')
    identifier(state.get('lead'))
    for task_id, task in state['tasks'].items():
        identifier(task_id)
        need(task.get('state') in STATES and task.get('kind') in {'implementation', 'validation'},
             'CORRUPT_REGISTRY')
        branch_name(task.get('branch'))
        scopes(task.get('paths'))
        scopes(task.get('contracts'), False)
        need(type(task.get('epoch')) is int and task['epoch'] >= 1, 'CORRUPT_REGISTRY')
    return legacy, state


def encode(legacy: str, state: dict) -> str:
    result = legacy + BEGIN + json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + END
    need(len(result.encode()) <= 450_000, 'REGISTRY_TOO_LARGE', 'archive history by reviewed migration')
    return result


def inventory_id(s: dict) -> str:
    return digest({k: s[k] for k in ('repo', 'main_head', 'base_code', 'registry_sha',
                                    'document', 'branches', 'prs')})


def validate_snapshot(s: dict, now: datetime) -> None:
    need(s.get('complete') is True and REPO.fullmatch(s.get('repo', '')), 'INCOMPLETE_SNAPSHOT')
    need(SHA.fullmatch(s.get('main_head', '')) and SHA.fullmatch(s.get('base_code', '')),
         'BAD_SNAPSHOT')
    need(isinstance(s.get('branches'), dict) and isinstance(s.get('prs'), list), 'BAD_SNAPSHOT')
    need(s['branches'].get('main') == s['main_head'], 'MAIN_MOVED')
    for name, head in s['branches'].items():
        branch_name(name)
        need(SHA.fullmatch(head), 'BAD_SNAPSHOT')
    for pr in s['prs']:
        need(pr.get('complete') is True and isinstance(pr.get('files'), list), 'INCOMPLETE_PR_FILES')
        need(s['branches'].get(pr['branch']) == pr['head'], 'PR_HEAD_MOVED')
    try:
        observed = datetime.fromisoformat(s['observed_at'])
        need(observed.tzinfo is not None, 'BAD_TIMESTAMP')
        need(-10 <= (now - observed).total_seconds() <= 300, 'STALE_SNAPSHOT')
    except (KeyError, TypeError, ValueError) as exc:
        raise Refused('BAD_TIMESTAMP') from exc


def _task(st: dict, q: dict) -> dict:
    key = identifier(q.get('task'))
    need(key in st['tasks'], 'TASK_NOT_FOUND')
    return st['tasks'][key]


def _owner(t: dict, q: dict) -> None:
    need(t['owner'] == q['actor'], 'NOT_OWNER')
    need(type(q.get('epoch')) is int and t['epoch'] == q['epoch'], 'STALE_LEASE')


def _head(t: dict, s: dict) -> None:
    need(s['branches'].get(t['branch']) == t['head'], 'HEAD_MOVED')


def _lead(st: dict, q: dict) -> None:
    need(q['actor'] == st['lead'], 'NOT_INTEGRATION_LEAD')


def _coverage(t: dict, paths: list[str]) -> None:
    for path in paths:
        path = scope(path)
        need(path != '**' and not path.endswith('/'), 'EXACT_CHANGED_PATH_REQUIRED')
        need(path.casefold() != REGISTRY.casefold(), 'REGISTRY_WRITE_FORBIDDEN')
        need(any(covers(p, path) for p in t['paths']), 'OUTSIDE_LEASE', path)


def _conflicts(st: dict, candidate: dict, except_id: str = '') -> None:
    for key, t in st['tasks'].items():
        if key == except_id or t['state'] in TERMINAL:
            continue
        need(t['branch'] != candidate['branch'], 'BRANCH_OWNED', key)
        need(t['feature'] != candidate['feature'], 'FEATURE_OWNED', key)
        for field in ('paths', 'contracts'):
            need(not any(intersects(a, b) for a in candidate[field] for b in t[field]),
                 'SCOPE_CONFLICT', f'{key}:{field}')


def _capacity(st: dict, s: dict, candidate: dict) -> None:
    live = [t for t in st['tasks'].values() if t['state'] not in TERMINAL]
    need(sum(t['kind'] == candidate['kind'] for t in live) <
         (1 if candidate['kind'] == 'validation' else 3), 'WIP_FULL')
    reserved = {t['branch'] for t in live}
    need(len(set(s['branches']) | reserved | {candidate['branch']}) <= 5, 'BRANCH_BUDGET_FULL')


def _inventory_review(q: dict, s: dict) -> None:
    need(q.get('inventory_id') == inventory_id(s), 'INVENTORY_CHANGED')
    text(q.get('inventory_review'))
    need(q.get('legacy_writers_accounted_for') is True, 'LEGACY_REVIEW_REQUIRED')


def _untracked(st: dict, s: dict) -> None:
    live = [t for t in st['tasks'].values() if t['state'] not in TERMINAL]
    need(all(any(pr['branch'] == t['branch'] and t.get('pr') in {None, pr['number']}
                 for t in live) for pr in s['prs']), 'UNREGISTERED_PR', 'reconcile inventory')


def _hold(st: dict, item: dict, s: dict, now: str) -> None:
    key = identifier(item['task'])
    need(key not in st['tasks'], 'TASK_EXISTS')
    branch = branch_name(item['branch'])
    need(branch != 'main' and branch in s['branches'], 'BAD_IMPORT_BRANCH')
    need(not any(t['branch'] == branch and t['state'] not in TERMINAL
                 for t in st['tasks'].values()), 'BRANCH_OWNED')
    pr = next((p for p in s['prs'] if p['branch'] == branch), None)
    paths = scopes(item.get('paths', (pr or {}).get('files') or ['**']))
    if pr:
        need(all(any(covers(p, f) for p in paths) for f in pr['files']), 'IMPORT_OMITS_FILES')
    kind = item.get('kind', 'validation' if branch.startswith('validation/') else 'implementation')
    need(kind in {'implementation', 'validation'}, 'BAD_KIND')
    need(not branch.startswith('validation/') or kind == 'validation', 'KIND_BRANCH_MISMATCH')
    st['tasks'][key] = dict(state='HOLD', owner=None, epoch=1, branch=branch,
        feature=text(item.get('feature', f'legacy/{branch}')).casefold(), paths=paths,
        contracts=scopes(item.get('contracts', []), False), kind=kind,
        head=s['branches'][branch], base=s['main_head'], risk='HIGH', tags=['LEGACY'],
        pr=pr['number'] if pr else None, dependencies=[], evidence={}, operation=None,
        created_at=now, updated_at=now, reason='legacy writer must be handed off; never auto-stolen')


def _proof(st: dict, t: dict, s: dict) -> None:
    ev = t.get('evidence', {})
    test = ev.get('tests', {})
    need(test.get('passed') is True and test.get('head') == t['head'] and
         test.get('base_code') == s['base_code'], 'TEST_EVIDENCE_REQUIRED')
    if t['risk'] == 'HIGH':
        rev = ev.get('security', {})
        need(rev.get('decision') == 'PASS' and rev.get('actor') != t['owner'] and
             rev.get('head') == t['head'] and rev.get('base_code') == s['base_code'],
             'SECURITY_REVIEW_REQUIRED')
    need(all(st['tasks'][key]['state'] in {'MERGED', 'VALIDATED'}
             for key in t['dependencies']), 'DEPENDENCY_BLOCKED')


def _pr(t: dict, s: dict, number: int) -> dict:
    pr = next((p for p in s['prs'] if p['number'] == number), None)
    need(pr and pr['branch'] == t['branch'] and pr['head'] == t['head'] and pr['base'] == 'main',
         'PR_MISMATCH')
    _coverage(t, pr['files'])
    need(pr.get('merge_base_code') == s['base_code'], 'BRANCH_NEEDS_SYNC')
    return pr


def plan(s: dict, q: dict, now: datetime | None = None) -> dict:
    """Return a CAS plan, never execute it. Callers MUST not blindly retry conflicts."""
    now = now or datetime.now(timezone.utc)
    validate_snapshot(s, now)
    actor = identifier(q.get('actor'))
    action = q.get('action')
    legacy, saved = decode(s['document'])
    st = copy.deepcopy(saved)
    request_hash = digest(q)
    request_id = identifier(q.get('request_id'))
    if st:
        need(st.get('repo') == s['repo'], 'WRONG_REPOSITORY')
        old = st['receipts'].get(request_id)
        if old:
            need(old['hash'] == request_hash, 'REQUEST_ID_REUSED')
            return dict(mutation=False, replay=True, receipt=old, document=s['document'])
        need(q.get('revision') == st['revision'], 'STALE_REVISION')
        if action != 'reconcile':
            need(st['legacy_digest'] == digest(legacy), 'LEGACY_CHANGED', 'lead must reconcile')
    stamp = now.isoformat()
    if action == 'init':
        need(st is None, 'ALREADY_INITIALIZED')
        _inventory_review(q, s)
        st = dict(schema=1, repo=s['repo'], revision=0, lead=actor, tasks={}, receipts={},
                  events=[], legacy_digest=digest(legacy), integration=None)
    else:
        need(st is not None, 'NOT_INITIALIZED', 'inspect and reviewed inventory first')
    if action in {'init', 'reconcile'}:
        _lead(st, q)
        _inventory_review(q, s)
        need(not st['integration'], 'INTEGRATION_BUSY')
        for item in q.get('imports', []):
            _hold(st, item, s, stamp)
        for pr in s['prs']:
            matched = next((t for t in st['tasks'].values() if t['branch'] == pr['branch']
                            and t['state'] not in TERMINAL), None)
            if matched:
                need(matched.get('pr') in {None, pr['number']}, 'MULTIPLE_PRS_FOR_BRANCH')
                matched['pr'] = pr['number']
            else:
                _hold(st, dict(task=f'legacy-pr-{pr["number"]}', branch=pr['branch']), s, stamp)
        st['legacy_digest'] = digest(legacy)
    elif action == 'transfer-lead':
        _lead(st, q)
        need(not st['integration'], 'INTEGRATION_BUSY')
        text(q.get('handoff'))
        st['lead'] = identifier(q.get('new_owner'))
    elif action == 'claim':
        _untracked(st, s)
        key = identifier(q.get('task'))
        need(key not in st['tasks'], 'TASK_EXISTS')
        text(q.get('preflight_evidence'))
        text(q.get('acceptance'))
        feature = text(q.get('feature')).casefold().strip()
        need(not any(t['feature'] == feature for t in st['tasks'].values()), 'FEATURE_EXISTS')
        branch = branch_name(q.get('branch'), new=True)
        need(branch not in s['branches'], 'EXISTING_BRANCH_REQUIRES_IMPORT')
        tags = q.get('tags', [])
        need(isinstance(tags, list) and tags and all(isinstance(x, str) for x in tags), 'TAGS_REQUIRED')
        risk = q.get('risk')
        need(risk in {'LOW', 'MEDIUM', 'HIGH'}, 'BAD_RISK')
        need(not (set(tags) & HIGH_TAGS) or risk == 'HIGH', 'RISK_UNDERESTIMATED')
        kind = q.get('kind', 'implementation')
        need(kind in {'implementation', 'validation'}, 'BAD_KIND')
        need((kind == 'validation') == branch.startswith('validation/'), 'KIND_BRANCH_MISMATCH')
        deps = q.get('dependencies', [])
        need(isinstance(deps, list) and all(k in st['tasks'] for k in deps), 'BAD_DEPENDENCY')
        t = dict(state='CLAIMED', owner=actor, epoch=1, branch=branch, feature=feature,
            paths=scopes(q.get('paths')), contracts=scopes(q.get('contracts', []), False),
            head=None, base=s['main_head'], risk=risk, kind=kind, tags=tags, pr=None,
            dependencies=deps, evidence={}, operation=None, created_at=stamp, updated_at=stamp,
            acceptance=q['acceptance'], preflight_evidence=q['preflight_evidence'])
        need('**' not in t['paths'], 'ROOT_SCOPE_FORBIDDEN')
        _coverage(t, [p for p in t['paths'] if p != '**' and not p.endswith('/')])
        _conflicts(st, t)
        _capacity(st, s, t)
        st['tasks'][key] = t
    else:
        t = _task(st, q)
        key = q['task']
        if action not in {'review', 'adopt', 'merge-start', 'merge-finish', 'merge-abort', 'cancel'}:
            _owner(t, q)
        if action not in {'create-finish', 'finish-write', 'finish-sync', 'merge-finish', 'adopt', 'cancel'} and t['head']:
            _head(t, s)
        if action in {'create-start', 'begin-write', 'begin-sync', 'submit', 'merge-start', 'adopt'}:
            _untracked(st, s)
        if action in {'create-start', 'begin-write'}:
            need(all(st['tasks'][dep]['state'] in {'MERGED', 'VALIDATED'} for dep in t['dependencies']),
                 'DEPENDENCY_BLOCKED')
        if action == 'adopt':
            _lead(st, q)
            need(t['state'] == 'HOLD' and q.get('previous_writer_stopped') is True, 'HANDOFF_REQUIRED')
            text(q.get('handoff_evidence'))
            need(q.get('head') == s['branches'].get(t['branch']), 'HEAD_MOVED')
            candidate = dict(t, head=q['head'], paths=scopes(q.get('paths')), contracts=scopes(q.get('contracts', []), False))
            if t.get('pr'):
                imported_pr = next((p for p in s['prs'] if p['number'] == t['pr']), None)
                need(imported_pr is not None, 'IMPORTED_PR_NOT_OPEN')
                _coverage(candidate, imported_pr['files'])
            _conflicts(st, candidate, key)
            t.update(candidate, owner=identifier(q.get('new_owner')), epoch=t['epoch'] + 1,
                     state='ACTIVE', head=q['head'], evidence={})
        elif action == 'create-start':
            need(t['state'] == 'CLAIMED' and t['branch'] not in s['branches'], 'BAD_STATE')
            reserved = {v['branch'] for v in st['tasks'].values() if v['state'] not in TERMINAL}
            need(len(set(s['branches']) | reserved) <= 5, 'BRANCH_BUDGET_FULL')
            t.update(state='BRANCHING', operation=dict(id=request_id, base=t['base']))
        elif action == 'create-abort':
            need(t['state'] == 'BRANCHING' and q.get('operation') == t['operation']['id'], 'BAD_OPERATION')
            need(t['branch'] not in s['branches'], 'BRANCH_EXISTS')
            t.update(state='CLAIMED', operation=None)
        elif action == 'create-finish':
            need(t['state'] == 'BRANCHING' and q.get('operation') == t['operation']['id'], 'BAD_OPERATION')
            need(s['branches'].get(t['branch']) == t['base'], 'BRANCH_COLLISION')
            t.update(state='ACTIVE', head=t['base'], operation=None)
        elif action == 'begin-sync':
            need(t['state'] in {'ACTIVE', 'READY'}, 'WRITE_NOT_QUIESCENT')
            t.update(state='SYNCING', evidence={}, operation=dict(id=request_id, head=t['head'],
                                                                 main=s['main_head']))
        elif action in {'finish-sync', 'abort-sync'}:
            need(t['state'] == 'SYNCING' and q.get('operation') == t['operation']['id'], 'BAD_OPERATION')
            if action == 'abort-sync':
                _head(t, s)
            else:
                proof = s.get('sync_proof', {})
                need(proof.get('old_head') == t['head'] and proof.get('main') == t['operation']['main']
                     and proof.get('head') == s['branches'].get(t['branch']) and proof.get('verified') is True,
                     'SYNC_PROOF_REQUIRED')
                t['head'] = proof['head']
            t.update(state='ACTIVE', operation=None)
        elif action == 'begin-write':
            need(t['state'] == 'ACTIVE', 'BAD_STATE')
            paths = scopes(q.get('paths'))
            _coverage(t, paths)
            _conflicts(st, t, key)
            t.update(state='WRITING', evidence={}, operation=dict(id=request_id, head=t['head'], paths=paths))
        elif action in {'finish-write', 'abort-write'}:
            need(t['state'] == 'WRITING' and q.get('operation') == t['operation']['id'], 'BAD_OPERATION')
            if action == 'abort-write':
                _head(t, s)
            else:
                proof = s.get('write_proof', {})
                head = s['branches'].get(t['branch'])
                need(head == q.get('new_head') and proof.get('base') == t['head'] and
                     proof.get('head') == head and proof.get('complete') is True and
                     proof.get('fast_forward') is True and proof.get('direct_parent') == t['head'],
                     'WRITE_PROOF_REQUIRED')
                _coverage(t, proof['files'])
                need(set(proof['files']) <= set(t['operation']['paths']), 'UNDECLARED_WRITE')
                t['head'] = head
            t.update(state='ACTIVE', operation=None)
        elif action == 'offer-handoff':
            need(t['state'] in {'ACTIVE', 'BLOCKED', 'READY'}, 'WRITE_NOT_QUIESCENT')
            t.update(state='HANDOFF', recipient=identifier(q.get('recipient')), epoch=t['epoch'] + 1,
                     evidence={}, handoff=text(q.get('handoff')))
        elif action == 'extend-scope':
            need(t['state'] == 'ACTIVE', 'WRITE_NOT_QUIESCENT')
            candidate = dict(t, paths=sorted(set(t['paths'] + scopes(q.get('paths', []), False))),
                             contracts=sorted(set(t['contracts'] + scopes(q.get('contracts', []), False))))
            need('**' not in candidate['paths'], 'ROOT_SCOPE_FORBIDDEN')
            _conflicts(st, candidate, key)
            text(q.get('reason'))
            t.update(candidate, evidence={})
        elif action in {'pause', 'resume'}:
            need(t['state'] in {'ACTIVE', 'BLOCKED'}, 'WRITE_NOT_QUIESCENT')
            t.update(state='BLOCKED' if action == 'pause' else 'ACTIVE', reason=text(q.get('reason')))
        elif action in {'tests', 'review'}:
            need(t['state'] in {'ACTIVE', 'READY'}, 'BAD_STATE')
            need(q.get('head') == t['head'] and q.get('base_code') == s['base_code'], 'STALE_EVIDENCE')
            evidence = dict(head=t['head'], base_code=s['base_code'], actor=actor,
                            report=text(q.get('report')), at=stamp)
            if action == 'tests':
                need(isinstance(q.get('passed'), bool), 'BAD_TEST_RESULT')
                evidence.update(passed=q['passed'], commands=text(q.get('commands')), attestation=True)
                t['evidence']['tests'] = evidence
            else:
                need(actor != t['owner'], 'SELF_REVIEW')
                need(q.get('decision') in {'PASS', 'FIX_REQUIRED', 'BLOCKED'}, 'BAD_REVIEW_RESULT')
                evidence['decision'] = q['decision']
                t['evidence']['security'] = evidence
        elif action == 'submit':
            need(t['state'] == 'ACTIVE', 'BAD_STATE')
            _proof(st, t, s)
            if t['kind'] == 'validation':
                t['state'] = 'VALIDATED'
            else:
                _pr(t, s, q.get('pr'))
                t.update(state='READY', pr=q['pr'])
        elif action == 'merge-start':
            _lead(st, q)
            need(t['state'] == 'READY' and not st['integration'], 'INTEGRATION_BUSY')
            _proof(st, t, s)
            pr = _pr(t, s, t['pr'])
            need(pr.get('draft') is False and pr.get('mergeable') is True, 'PR_NOT_MERGEABLE')
            st['integration'] = dict(task=key, id=request_id, owner=actor, head=t['head'],
                                     base_code=s['base_code'], pr=t['pr'])
            t['state'] = 'INTEGRATING'
        elif action in {'merge-finish', 'merge-abort'}:
            _lead(st, q)
            lock = st.get('integration') or {}
            need(lock.get('task') == key and lock.get('id') == q.get('operation'), 'BAD_OPERATION')
            if action == 'merge-abort':
                pr = _pr(t, s, t['pr'])
                need(pr and s['base_code'] == lock['base_code'], 'MERGE_OUTCOME_UNKNOWN')
                t['state'] = 'READY'
            else:
                proof = s.get('merge_proof', {})
                need(proof.get('merged') is True and proof.get('pr') == t['pr'] and
                     proof.get('head') == lock['head'] and proof.get('before_code') == lock['base_code']
                     and proof.get('after_code') == s['base_code'] and proof.get('in_main') is True,
                     'MERGE_PROOF_REQUIRED')
                t.update(state='MERGED', merge_sha=proof['merge_sha'])
            st['integration'] = None
        elif action == 'cancel':
            _lead(st, q)
            need(t['state'] not in {'WRITING', 'BRANCHING', 'SYNCING', 'INTEGRATING'} | TERMINAL, 'WRITE_NOT_QUIESCENT')
            t.update(state='CANCELLED', reason=text(q.get('approval')), epoch=t['epoch'] + 1)
        else:
            raise Refused('UNKNOWN_ACTION')
        t['updated_at'] = stamp
    st['revision'] += 1
    receipt = dict(hash=request_hash, revision=st['revision'], action=action, actor=actor, at=stamp)
    st['receipts'][request_id] = receipt
    st['events'].append(dict(id=request_id, task=q.get('task'), **receipt))
    document = encode(legacy, st)
    return dict(mutation=True, document=document, state=st, receipt=receipt,
                expected_sha=s['registry_sha'], expected_main=s['main_head'], repo=s['repo'],
                registry_path=REGISTRY, inventory_id=inventory_id(s))


def accept(s: dict, q: dict, now: datetime | None = None) -> dict:
    """Handoff acceptance uses the recipient identity and new fencing epoch."""
    now = now or datetime.now(timezone.utc)
    validate_snapshot(s, now)
    legacy, st = decode(s['document'])
    need(st and st['repo'] == s['repo'] and st['legacy_digest'] == digest(legacy), 'REGISTRY_CHANGED')
    previous = st['receipts'].get(q.get('request_id'))
    if previous:
        need(previous['hash'] == digest(q), 'REQUEST_ID_REUSED')
        return dict(mutation=False, replay=True, receipt=previous, document=s['document'])
    t = _task(st, q)
    need(t['state'] == 'HANDOFF' and t['recipient'] == q.get('actor'), 'NOT_RECIPIENT')
    need(t['epoch'] == q.get('epoch') and st['revision'] == q.get('revision'), 'STALE_LEASE')
    _head(t, s)
    identifier(q['actor']); identifier(q['request_id'])
    need(q['request_id'] not in st['receipts'], 'REQUEST_ID_REUSED')
    t.update(owner=q['actor'], epoch=t['epoch'] + 1, state='ACTIVE', evidence={},
             updated_at=now.isoformat())
    del t['recipient']
    st['revision'] += 1
    receipt = dict(hash=digest(q), revision=st['revision'], action='accept', actor=q['actor'], at=now.isoformat())
    st['receipts'][q['request_id']] = receipt
    st['events'].append(dict(id=q['request_id'], task=q['task'], **receipt))
    return dict(mutation=True, document=encode(legacy, st), state=st, receipt=receipt,
                expected_sha=s['registry_sha'], expected_main=s['main_head'], repo=s['repo'], registry_path=REGISTRY)


def check(s: dict, q: dict, now: datetime | None = None) -> dict:
    """Read-only check of an acquired write operation, not a server-side ACL."""
    validate_snapshot(s, now or datetime.now(timezone.utc))
    legacy, st = decode(s['document'])
    need(st and st['repo'] == s['repo'] and st['legacy_digest'] == digest(legacy), 'REGISTRY_CHANGED')
    t = _task(st, q)
    _owner(t, q); _head(t, s); _untracked(st, s); _conflicts(st, t, q['task'])
    need(t['state'] == 'WRITING' and t['operation']['id'] == q.get('operation'), 'WRITE_NOT_ACQUIRED')
    paths = scopes(q.get('paths'))
    _coverage(t, paths)
    need(set(paths) <= set(t['operation']['paths']), 'UNDECLARED_WRITE')
    return dict(allowed=True, task=q['task'], branch=t['branch'], head=t['head'],
                epoch=t['epoch'], operation=t['operation']['id'], paths=paths)
