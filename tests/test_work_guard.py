"""Offline regression + service/REST contracts. Never touches product repositories."""
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from tools.work_guard import core
from tools.work_guard.github import GitHub, NoRedirect
from tools.work_guard.service import Guard


def sha(value):
    return hashlib.sha1(str(value).encode()).hexdigest()


def blob(text):
    data = text.encode()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class FakeGitHub:
    """Atomic CAS in memory; separate code and registry commits, injected failures."""
    def __init__(self):
        self.repo = 'owner/product'
        self.document_text = '# Existing policy\r\n\nDo not touch existing work.\n'
        self.branches = {'main': sha('main')}
        self.base_code = sha('code-tree')
        self.prs = []
        self.saves = 0
        self.lock = threading.Lock()
        self.parents = {}
        self.changed = {}
        self.fail_create = False
        self.fail_publish = False
        self.merge_calls = 0
        self.merged = {}

    def snapshot(self):
        with self.lock:
            return dict(repo=self.repo, document=self.document_text, registry_sha=blob(self.document_text),
                main_head=self.branches['main'], base_code=self.base_code,
                branches=copy.deepcopy(self.branches), prs=copy.deepcopy(self.prs), complete=True,
                observed_at=datetime.now(timezone.utc).isoformat())

    def save(self, plan):
        with self.lock:
            core.need(plan['expected_sha'] == blob(self.document_text), 'CAS_CONFLICT')
            self.document_text = plan['document']
            self.saves += 1
            self.branches['main'] = sha('registry-' + str(self.saves))
            return {'content': {'sha': blob(self.document_text)}}

    def create_branch(self, name, parent):
        with self.lock:
            core.need(name not in self.branches, 'BRANCH_EXISTS')
            self.branches[name] = parent
        if self.fail_create:
            raise core.Refused('API_OUTCOME_UNKNOWN')

    def publish(self, name, parent, files, message):
        with self.lock:
            core.need(self.branches[name] == parent, 'HEAD_MOVED')
            head = sha(parent + json.dumps(files, sort_keys=True))
            self.branches[name] = head
            self.parents[head] = parent
            self.changed[head] = sorted(files)
            for p in self.prs:
                if p['branch'] == name:
                    p['head'] = head
                    p['files'] = sorted(set(p['files']) | set(files))
        if self.fail_publish:
            raise core.Refused('API_OUTCOME_UNKNOWN')
        return head

    def write_proof(self, parent, head):
        return dict(base=parent, head=head, complete=True, fast_forward=self.parents.get(head) == parent,
                    direct_parent=self.parents.get(head), files=self.changed.get(head, []))

    def merge(self, number, head):
        with self.lock:
            p = next(p for p in self.prs if p['number'] == number)
            core.need(p['head'] == head, 'HEAD_MOVED')
            self.merge_calls += 1
            merged = sha('merge' + head)
            after = sha('code-tree:' + merged)
            self.merged[number] = dict(pr=number, merged=True, head=head, merge_sha=merged,
                                       before_code=self.base_code, after_code=after, in_main=True)
            self.base_code = after
            self.branches['main'] = merged
            self.prs.remove(p)
            return dict(merged=True, sha=merged)

    def merge_proof(self, number, main):
        return copy.deepcopy(self.merged[number])

    def sync(self, branch, main):
        head = sha('sync:' + self.branches[branch] + main)
        self.parents[head] = [self.branches[branch], main]
        self.branches[branch] = head
        for pr in self.prs:
            if pr['branch'] == branch:
                pr['head'] = head
                pr['merge_base_code'] = self.base_code

    def sync_proof(self, old_head, main, head):
        return dict(old_head=old_head, main=main, head=head,
                    verified=self.parents.get(head) == [old_head, main])


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()
        self.guard = Guard(self.api)
        self.counter = 0
        self.initialize()

    def test_closed_imported_pr_cannot_be_adopted_silently(self):
        self.api.branches['work/old'] = sha('old')
        self.api.prs.append(dict(number=7, branch='work/old', head=sha('old'), base='main',
            files=['src/old/x.py'], complete=True, draft=False, mergeable=True,
            merge_base_code=self.api.base_code))
        snap = self.api.snapshot()
        self.guard.transition(self.q('reconcile', actor='lead', inventory_id=core.inventory_id(snap),
            inventory_review='Existing PR verified', legacy_writers_accounted_for=True))
        self.api.prs = []
        with self.assertRaisesRegex(core.Refused, 'IMPORTED_PR_NOT_OPEN'):
            self.guard.transition(self.q('adopt', actor='lead', task='legacy-pr-7',
                previous_writer_stopped=True, handoff_evidence='Writer stopped',
                new_owner='writer-b', head=sha('old'), paths=['src/old/']))

    def state(self):
        return core.decode(self.api.document_text)[1]

    def q(self, action, actor='writer-a', task='A', **kw):
        self.counter += 1
        st = self.state()
        result = dict(action=action, actor=actor, task=task, request_id='r' + str(self.counter),
                      revision=st['revision'] if st else 0,
                      epoch=st['tasks'].get(task, {}).get('epoch', 1) if st else 1)
        result.update(kw)
        return result

    def initialize(self):
        s = self.api.snapshot()
        self.guard.transition(self.q('init', actor='lead', inventory_id=core.inventory_id(s),
            inventory_review='Reviewed exact prose, refs, open PRs; no external active writer.',
            legacy_writers_accounted_for=True))

    def claim(self, task='A', actor='writer-a', paths=None, contracts=None, kind='implementation', risk='LOW', tags=None):
        return self.guard.transition(self.q('claim', actor=actor, task=task,
            branch=('validation/' if kind == 'validation' else 'work/') + task.lower(),
            feature=f'feature/{task}', paths=paths or [f'src/{task}/'], contracts=contracts or [],
            kind=kind, risk=risk, tags=tags or ['UI'], acceptance='Complete this scoped feature.',
            preflight_evidence='Searched main and active PRs; no duplicate implementation.'))

    def active(self, task='A', actor='writer-a', **kw):
        self.claim(task=task, actor=actor, **kw)
        self.guard.create_branch(self.q('create-branch', actor=actor, task=task))
        return self.state()['tasks'][task]

    def add_pr(self, task='A', number=1, files=None):
        t = self.state()['tasks'][task]
        self.api.prs.append(dict(number=number, branch=t['branch'], head=t['head'], base='main',
            files=files or [f'src/{task}/x.py'], complete=True, draft=False, mergeable=True, merge_base_code=self.api.base_code))

    def evidence(self, task='A', actor='writer-a', passed=True):
        t = self.state()['tasks'][task]
        self.guard.transition(self.q('tests', actor=actor, task=task, head=t['head'],
            base_code=self.api.base_code, commands='python -m unittest', passed=passed, report='logs/test-sha.txt'))

    def review(self, task='A', actor='reviewer', decision='PASS'):
        t = self.state()['tasks'][task]
        self.guard.transition(self.q('review', actor=actor, task=task, head=t['head'],
            base_code=self.api.base_code, decision=decision, report='review: PR diff and negative tests examined'))

    def ready(self, task='A', actor='writer-a', number=1, high=False):
        self.active(task, actor, risk='HIGH' if high else 'LOW')
        self.add_pr(task, number)
        self.evidence(task, actor)
        if high:
            self.review(task)
        self.guard.transition(self.q('submit', actor=actor, task=task, pr=number))

    def refuses(self, code, func, *args, **kwargs):
        with self.assertRaises(core.Refused) as caught:
            func(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_legacy_prose_preserved_exactly(self):
        legacy, _ = core.decode(self.api.document_text)
        self.assertEqual(legacy, '# Existing policy\r\n\nDo not touch existing work.\n')

    def test_same_snapshot_concurrent_claim_only_one_CAS_wins(self):
        s = self.api.snapshot()
        q1 = self.q('claim', branch='work/first', feature='signup', paths=['src/auth/'],
                    acceptance='signup works', preflight_evidence='main inspected', tags=['UI'], risk='LOW')
        q2 = dict(q1, actor='writer-b', task='B', request_id='competing', branch='work/second')
        plans = [core.plan(s, q1), core.plan(s, q2)]
        barrier = threading.Barrier(2)
        def attempt(p):
            barrier.wait()
            try:
                self.api.save(p)
                return 'saved'
            except core.Refused as e:
                return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, plans))
        self.assertCountEqual(results, ['saved', 'CAS_CONFLICT'])
        self.assertEqual(len(self.state()['tasks']), 1)

    def test_semantic_key_duplicate(self):
        self.claim()
        q = self.q('claim', actor='writer-b', task='B', branch='work/b', feature='FEATURE/A',
            paths=['src/other/'], tags=['UI'], risk='LOW', acceptance='x', preflight_evidence='x')
        self.refuses('FEATURE_EXISTS', self.guard.transition, q)

    def test_parent_child_path_conflict(self):
        self.claim(paths=['src/auth/**'])
        self.refuses('SCOPE_CONFLICT', self.claim, task='B', actor='writer-b', paths=['src/auth/login.ts'])

    def test_case_insensitive_path_conflict_conservative(self):
        self.claim(paths=['src/Auth/'])
        self.refuses('SCOPE_CONFLICT', self.claim, task='B', actor='writer-b', paths=['SRC/auth/x.py'])

    def test_contract_conflict_even_with_different_files(self):
        self.claim(contracts=['auth/session'])
        self.refuses('SCOPE_CONFLICT', self.claim, task='B', actor='writer-b', contracts=['auth/session'])

    def test_disjoint_paths_and_contracts_parallel(self):
        self.claim(); self.claim('B', 'writer-b')
        self.assertEqual(len(self.state()['tasks']), 2)

    def test_branch_actual_refs_and_pending_slots_both_count(self):
        self.api.branches.update({f'old/{i}': sha(i) for i in range(3)})
        self.claim()
        self.refuses('BRANCH_BUDGET_FULL', self.claim, 'B', 'writer-b')

    def test_over_budget_does_not_prevent_existing_owner_fix(self):
        self.active()
        self.api.branches.update({f'old/{i}': sha(i) for i in range(20)})
        self.guard.write(self.q('write'), {'src/A/x.py': 'x = 1\n'}, 'fix: within existing lease')
        self.assertEqual(self.state()['tasks']['A']['state'], 'ACTIVE')

    def test_three_WIP_slots_include_blocked_and_ready(self):
        self.active(); self.guard.transition(self.q('pause', reason='environment blocked'))
        self.claim('B', 'writer-b'); self.claim('C', 'writer-c')
        self.refuses('WIP_FULL', self.claim, 'D', 'writer-d')

    def test_validation_has_one_separate_slot(self):
        self.claim(kind='validation')
        self.refuses('WIP_FULL', self.claim, 'B', 'writer-b', kind='validation')

    def test_read_only_inspect_never_creates_branch_or_write(self):
        before = self.api.saves
        for _ in range(5): self.guard.inspect()
        self.assertEqual(before, self.api.saves)
        self.assertEqual(len(self.api.branches), 1)

    def test_branch_creation_requires_claim(self):
        self.refuses('TASK_NOT_FOUND', self.guard.create_branch, self.q('create-branch'))

    def test_unknown_create_outcome_keeps_lock_and_can_finish(self):
        self.claim(); q = self.q('create-branch'); self.api.fail_create = True
        self.refuses('API_OUTCOME_UNKNOWN', self.guard.create_branch, q)
        self.assertEqual(self.state()['tasks']['A']['state'], 'BRANCHING')
        self.guard.transition(self.q('create-finish', operation=q['request_id']))
        self.assertEqual(self.state()['tasks']['A']['state'], 'ACTIVE')

    def test_wrong_owner_cannot_write(self):
        self.active()
        self.refuses('NOT_OWNER', self.guard.write, self.q('write', actor='writer-b'), {'src/A/x': 'x'}, 'x')

    def test_direct_guard_check_without_begin_refused(self):
        self.active()
        self.refuses('WRITE_NOT_ACQUIRED', core.check, self.api.snapshot(), self.q('check', paths=['src/A/x']))

    def test_outside_scope_write_refused_before_commit(self):
        self.active()
        self.refuses('OUTSIDE_LEASE', self.guard.write, self.q('write'), {'src/B/x.py': 'x'}, 'x')
        self.assertEqual(self.state()['tasks']['A']['state'], 'ACTIVE')

    def test_registry_is_not_product_write_target(self):
        self.active(paths=['src/'])
        self.refuses('REGISTRY_WRITE_FORBIDDEN', self.guard.write, self.q('write'), {'ACTIVE_WORK.md': 'x'}, 'x')

    def test_force_moved_branch_is_not_silently_accepted(self):
        self.active(); self.api.branches['work/a'] = sha('foreign')
        self.refuses('HEAD_MOVED', self.guard.write, self.q('write'), {'src/A/x.py': 'x'}, 'x')

    def test_unknown_write_outcome_blocks_handoff_and_can_recover(self):
        self.active(); self.api.fail_publish = True; q = self.q('write')
        self.refuses('API_OUTCOME_UNKNOWN', self.guard.write, q, {'src/A/x.py': 'x'}, 'x')
        self.refuses('HEAD_MOVED', self.guard.transition, self.q('offer-handoff', recipient='writer-b', handoff='stopped'))
        self.guard.transition(self.q('finish-write', operation=q['request_id'], new_head=self.api.branches['work/a']))
        self.assertEqual(self.state()['tasks']['A']['state'], 'ACTIVE')

    def test_unquiescent_writer_cannot_cancel(self):
        self.active(); self.guard.transition(self.q('begin-write', paths=['src/A/x.py']))
        self.refuses('WRITE_NOT_QUIESCENT', self.guard.transition, self.q('cancel', actor='lead', approval='user asked'))

    def test_handoff_uses_same_branch_fences_old_epoch(self):
        self.active(); old_epoch = self.state()['tasks']['A']['epoch']
        self.guard.transition(self.q('offer-handoff', recipient='writer-b', handoff='No write in flight; HEAD checked.'))
        self.guard.transition(self.q('accept', actor='writer-b'))
        self.assertEqual(self.state()['tasks']['A']['branch'], 'work/a')
        self.refuses('NOT_OWNER', self.guard.write, self.q('write', epoch=old_epoch), {'src/A/x': 'x'}, 'x')
        self.guard.write(self.q('write', actor='writer-b'), {'src/A/x': 'x'}, 'x')

    def test_handoff_only_intended_recipient_can_accept(self):
        self.active(); self.guard.transition(self.q('offer-handoff', recipient='writer-b', handoff='stopped'))
        self.refuses('NOT_RECIPIENT', self.guard.transition, self.q('accept', actor='writer-c'))

    def test_branch_needs_sync_after_other_work_merged(self):
        self.active(); self.add_pr()
        self.api.base_code = sha('new-main-code')
        self.evidence()
        self.refuses('BRANCH_NEEDS_SYNC', self.guard.transition, self.q('submit', pr=1))
        self.guard.sync(self.q('sync'))
        self.assertFalse(self.state()['tasks']['A']['evidence'])
        self.evidence(); self.guard.transition(self.q('submit', pr=1))
        self.assertEqual(self.state()['tasks']['A']['state'], 'READY')

    def test_sync_blocks_handoff_until_verified(self):
        self.active(); self.guard.transition(self.q('begin-sync'))
        self.refuses('WRITE_NOT_QUIESCENT', self.guard.transition,
                     self.q('offer-handoff', recipient='writer-b', handoff='not yet safe'))

    def test_dependency_not_merged_blocks_branch_creation(self):
        self.claim()
        q = self.q('claim', actor='writer-b', task='B', branch='work/b', feature='dependent',
                   paths=['src/B/'], tags=['UI'], risk='LOW', acceptance='x', preflight_evidence='x', dependencies=['A'])
        self.guard.transition(q)
        self.refuses('DEPENDENCY_BLOCKED', self.guard.create_branch,
                     self.q('create-branch', task='B', actor='writer-b'))

    def test_draft_pr_never_merged(self):
        self.ready(); self.api.prs[0]['draft'] = True
        self.refuses('PR_NOT_MERGEABLE', self.guard.merge, self.q('merge', actor='lead', approval='reviewed'))

    def test_stale_lease_epoch_rejected_even_same_owner(self):
        self.active()
        self.refuses('STALE_LEASE', self.guard.transition, self.q('begin-write', epoch=0, paths=['src/A/x']))

    def test_failed_tests_do_not_unlock_merge(self):
        self.active(); self.add_pr(); self.evidence(passed=False)
        self.refuses('TEST_EVIDENCE_REQUIRED', self.guard.transition, self.q('submit', pr=1))

    def test_missing_tests_block_submit(self):
        self.active(); self.add_pr()
        self.refuses('TEST_EVIDENCE_REQUIRED', self.guard.transition, self.q('submit', pr=1))

    def test_high_risk_requires_distinct_review(self):
        self.active(risk='HIGH', tags=['AUTH']); self.add_pr(); self.evidence()
        self.refuses('SELF_REVIEW', self.review, actor='writer-a')
        self.refuses('SECURITY_REVIEW_REQUIRED', self.guard.transition, self.q('submit', pr=1))
        self.review(); self.guard.transition(self.q('submit', pr=1))

    def test_medium_auth_risk_cannot_be_mislabeled(self):
        self.refuses('RISK_UNDERESTIMATED', self.claim, risk='MEDIUM', tags=['AUTH'])

    def test_changed_base_invalidates_test_attestation(self):
        self.active(); self.add_pr(); self.evidence()
        self.api.base_code = sha('new-real-code')
        self.refuses('TEST_EVIDENCE_REQUIRED', self.guard.transition, self.q('submit', pr=1))

    def test_registry_only_updates_do_not_invalidate_evidence(self):
        self.active(); self.add_pr(); self.evidence()
        self.review()  # adds a main registry commit, base_code is unchanged
        self.guard.transition(self.q('submit', pr=1))
        self.assertEqual(self.state()['tasks']['A']['state'], 'READY')

    def test_new_write_clears_old_tests(self):
        self.active(); self.evidence()
        self.guard.write(self.q('write'), {'src/A/x.py': 'updated'}, 'x')
        self.assertFalse(self.state()['tasks']['A']['evidence'])

    def test_new_unregistered_PR_blocks_further_claims(self):
        self.api.branches['work/foreign'] = sha('foreign')
        self.api.prs.append(dict(number=8, branch='work/foreign', head=sha('foreign'), base='main',
                                complete=True, files=['src/z.py'], draft=True, mergeable=None, merge_base_code=self.api.base_code))
        self.refuses('UNREGISTERED_PR', self.claim)

    def test_reconcile_imports_unknown_PR_as_hold_not_owner(self):
        self.api.branches['work/foreign'] = sha('foreign')
        self.api.prs.append(dict(number=8, branch='work/foreign', head=sha('foreign'), base='main',
                                complete=True, files=['src/z.py'], draft=True, mergeable=None, merge_base_code=self.api.base_code))
        s = self.api.snapshot()
        self.guard.transition(self.q('reconcile', actor='lead', inventory_id=core.inventory_id(s),
            inventory_review='Reviewed legacy writer with PR owner.', legacy_writers_accounted_for=True))
        t = self.state()['tasks']['legacy-pr-8']
        self.assertIsNone(t['owner']); self.assertEqual(t['state'], 'HOLD')

    def test_original_prose_edit_requires_reconciliation(self):
        self.api.document_text = 'New external task\n' + self.api.document_text
        self.refuses('LEGACY_CHANGED', self.claim)

    def test_reconciliation_preserves_updated_prose(self):
        self.api.document_text = 'New note\n' + self.api.document_text
        s = self.api.snapshot()
        self.guard.transition(self.q('reconcile', actor='lead', inventory_id=core.inventory_id(s),
            inventory_review='Reviewed added note, no writer.', legacy_writers_accounted_for=True))
        self.claim(); self.assertTrue(self.api.document_text.startswith('New note\n'))

    def test_stale_inventory_cannot_be_initialized(self):
        api = FakeGitHub(); s = api.snapshot()
        q = dict(action='init', actor='lead', request_id='init', inventory_id=core.inventory_id(s),
                 inventory_review='Reviewed', legacy_writers_accounted_for=True)
        api.branches['work/race'] = sha('race')
        self.refuses('INVENTORY_CHANGED', Guard(api).transition, q)

    def test_stale_revision_does_not_auto_refresh(self):
        q = self.q('transfer-lead', actor='lead', new_owner='lead-two', handoff='stopped')
        self.claim()
        self.refuses('STALE_REVISION', self.guard.transition, q)

    def test_same_request_retry_returns_receipt_not_second_mutation(self):
        q = self.q('transfer-lead', actor='lead', new_owner='lead-two', handoff='stopped')
        self.guard.transition(q); before = self.api.saves
        result = self.guard.transition(q)
        self.assertTrue(result['replay']); self.assertEqual(before, self.api.saves)

    def test_request_id_reuse_with_different_payload_fails(self):
        q = self.q('transfer-lead', actor='lead', new_owner='lead-two', handoff='stopped')
        self.guard.transition(q)
        self.refuses('REQUEST_ID_REUSED', self.guard.transition, dict(q, new_owner='other'))

    def test_only_lead_may_merge(self):
        self.ready()
        self.refuses('NOT_INTEGRATION_LEAD', self.guard.merge, self.q('merge', approval='approved'))
        self.assertEqual(self.api.merge_calls, 0)

    def test_merge_end_to_end_retains_branch_for_approved_cleanup(self):
        self.ready(high=True)
        self.guard.merge(self.q('merge', actor='lead', approval='Explicit reviewed integration'))
        self.assertEqual(self.state()['tasks']['A']['state'], 'MERGED')
        self.assertIn('work/a', self.api.branches)
        self.assertIsNone(self.state()['integration'])

    def test_only_one_merge_in_flight(self):
        self.ready(); self.ready('B', 'writer-b', 2)
        self.guard.transition(self.q('merge-start', actor='lead'))
        self.refuses('INTEGRATION_BUSY', self.guard.transition, self.q('merge-start', actor='lead', task='B'))

    def test_unknown_merge_base_does_not_mark_done(self):
        self.ready(); q = self.q('merge-start', actor='lead'); self.guard.transition(q)
        t = self.state()['tasks']['A']; self.api.merge(1, t['head'])
        self.api.merged[1]['before_code'] = sha('unreviewed-base')
        self.refuses('MERGE_PROOF_REQUIRED', self.guard.transition,
                     self.q('merge-finish', actor='lead', operation=q['request_id']))
        self.assertEqual(self.state()['tasks']['A']['state'], 'INTEGRATING')

    def test_closed_pr_does_not_create_branch_slot(self):
        self.ready(); self.guard.transition(self.q('cancel', actor='lead', approval='user approved abandonment'))
        self.api.prs.clear()
        self.api.branches.update({f'old/{i}': sha(i) for i in range(3)})
        self.refuses('BRANCH_BUDGET_FULL', self.claim, 'B', 'writer-b')

    def test_unregistered_existing_branch_cannot_be_claimed(self):
        self.api.branches['work/a'] = sha('old')
        self.refuses('EXISTING_BRANCH_REQUIRES_IMPORT', self.claim)

    def test_scope_extension_same_branch(self):
        self.active()
        self.guard.transition(self.q('extend-scope', paths=['tests/A/'], reason='Add regression tests.'))
        self.guard.write(self.q('write'), {'tests/A/test_x.py': 'assert True'}, 'test: scoped')
        self.assertEqual(len(self.api.branches), 2)

    def test_conflicting_scope_extension_rejected(self):
        self.active(); self.claim('B', 'writer-b')
        self.refuses('SCOPE_CONFLICT', self.guard.transition,
                     self.q('extend-scope', paths=['src/B/'], reason='cannot take another scope'))

    def test_expired_snapshot_refused(self):
        s = self.api.snapshot(); s['observed_at'] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        self.refuses('STALE_SNAPSHOT', core.plan, s, self.q('transfer-lead', actor='lead', new_owner='lead2', handoff='x'))

    def test_incomplete_snapshot_refused(self):
        s = self.api.snapshot(); s['complete'] = False
        self.refuses('INCOMPLETE_SNAPSHOT', core.plan, s, self.q('unknown'))

    def test_corrupt_markers_fail_closed(self):
        self.refuses('CORRUPT_REGISTRY', core.decode, self.api.document_text + core.BEGIN)

    def test_duplicate_json_keys_fail_closed(self):
        self.refuses('DUPLICATE_JSON_KEY', core.decode,
                     'legacy' + core.BEGIN + '{"schema":1,"schema":1}' + core.END)

    def test_unknown_schema_not_silently_replaced(self):
        legacy, st = core.decode(self.api.document_text); st['schema'] = 2
        self.refuses('SCHEMA_UNSUPPORTED', core.decode, core.encode(legacy, st))

    def test_unsafe_paths_and_patterns_rejected(self):
        for path in ['../secrets', '/etc/passwd', 'C:\\secrets', 'src/../../x', 'src/*/x', 'src//x', 'src/./x']:
            with self.subTest(path=path): self.refuses('BAD_SCOPE', core.scope, path)

    def test_new_root_wildcard_refused(self):
        self.refuses('ROOT_SCOPE_FORBIDDEN', self.claim, paths=['**'])

    def test_bad_revision_branch_names_rejected(self):
        for name in ['backup/main', 'work/auth-final2', 'work/auth-v2', 'work/../x', 'work/a.lock']:
            with self.subTest(name=name):
                with self.assertRaises(core.Refused): core.branch_name(name, new=True)

    def test_lease_age_does_not_auto_release(self):
        self.claim(); legacy, st = core.decode(self.api.document_text)
        st['tasks']['A']['updated_at'] = '2001-01-01T00:00:00+00:00'
        self.api.document_text = core.encode(legacy, st)
        self.refuses('SCOPE_CONFLICT', self.claim, 'B', 'writer-b', paths=['src/A/'])

    def test_receipt_and_revision_monotonically_advance(self):
        before = self.state()['revision']; self.claim(); self.active('B', 'writer-b')
        self.assertGreater(self.state()['revision'], before)
        self.assertEqual(len(self.state()['events']), self.state()['revision'])

    def test_offline_plan_does_not_reserve(self):
        before = self.api.document_text
        q = self.q('transfer-lead', actor='lead', new_owner='next-lead', handoff='stopped')
        with tempfile.TemporaryDirectory() as directory:
            s = Path(directory) / 'snapshot.json'; r = Path(directory) / 'request.json'
            s.write_text(json.dumps(self.api.snapshot())); r.write_text(json.dumps(q))
            process = subprocess.run([sys.executable, '-m', 'tools.work_guard', 'plan',
                '--snapshot', str(s), '--request', str(r)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertTrue(result['dry_run']); self.assertIn('connector_write', result)
        self.assertEqual(before, self.api.document_text)


class TransportTests(unittest.TestCase):
    def test_pagination_reads_more_than_first_hundred(self):
        api = GitHub('owner/product', '')
        api.call = lambda m, p: [0] * 100 if '&page=1' in p else [1] * 3
        self.assertEqual(len(api.pages('/branches')), 103)

    def test_pagination_at_cap_refuses_false_completeness(self):
        api = GitHub('owner/product', '')
        api.call = lambda *a: [0] * 100
        with self.assertRaises(core.Refused) as e: api.pages('/branches', 100)
        self.assertEqual(e.exception.code, 'INCOMPLETE_PAGINATION')

    def test_write_requires_environment_token(self):
        api = GitHub('owner/product', '')
        with self.assertRaises(core.Refused) as e: api.call('POST', '/git/refs', {})
        self.assertEqual(e.exception.code, 'TOKEN_REQUIRED')

    def test_http_conflict_not_retried_or_body_logged(self):
        api = GitHub('owner/product', 'do-not-print-this-token')
        calls = []
        class Opener:
            def open(self, req, timeout):
                calls.append(req)
                raise HTTPError(req.full_url, 409, 'private-error-secret', {}, io.BytesIO(b'secret'))
        api._opener = Opener()
        with self.assertRaises(core.Refused) as e: api.call('PUT', '/contents/ACTIVE_WORK.md', {})
        self.assertEqual(str(e.exception), 'CAS_CONFLICT'); self.assertEqual(len(calls), 1)

    def test_redirect_never_forwards_bearer_token(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))

    def test_metadata_only_changes_share_code_fingerprint(self):
        api = GitHub('owner/product', '')
        api.commit = lambda sha: {'tree': {'sha': sha}}
        def call(method, path):
            return dict(truncated=False, tree=[
                dict(path='src', mode='040000', type='tree', sha=sha('same-code')),
                dict(path='ACTIVE_WORK.md', mode='100644', type='blob', sha=sha(path))])
        api.call = call
        self.assertEqual(api.code_fingerprint('a' * 40), api.code_fingerprint('b' * 40))

    def test_compare_truncation_is_not_accepted(self):
        api = GitHub('owner/product', '')
        api.call = lambda *args: dict(files=[{'filename': str(x)} for x in range(300)])
        with self.assertRaises(core.Refused) as e: api.write_proof('a' * 40, 'b' * 40)
        self.assertEqual(e.exception.code, 'INCOMPLETE_DIFF')

    def test_compare_route_is_not_rejected_as_path_traversal(self):
        api = GitHub('owner/product', '')
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, maximum): return b'{"status":"ahead"}'
        class Opener:
            def open(self, req, timeout): return Response()
        api._opener = Opener()
        self.assertEqual(api.call('GET', '/compare/' + 'a' * 40 + '...' + 'b' * 40)['status'], 'ahead')

    def test_wrong_repository_identifier_rejected(self):
        for repo in ['../product', 'https://evil.invalid/repo', 'owner/repo/extra', 'owner/..']:
            with self.subTest(repo=repo):
                with self.assertRaises(core.Refused): GitHub(repo, '')

    def test_snapshot_reads_consistent_remote_shapes(self):
        import base64
        api = GitHub('owner/product', '')
        main, work = sha('main'), sha('work')
        doc = '# preserved'
        seen = []
        def call(method, path, data=None):
            seen.append(path)
            if path == '/git/ref/heads/main': return {'object': {'sha': main}}
            if path.startswith('/contents/'):
                return dict(type='file', encoding='base64', sha=blob(doc), content=base64.b64encode(doc.encode()).decode())
            if path.startswith('/branches?'):
                return [dict(name='main', commit={'sha': main}), dict(name='work/a', commit={'sha': work})]
            if path.startswith('/pulls?'): return [{'number': 1}]
            if path == '/pulls/1':
                return dict(number=1, state='open', changed_files=1, draft=False, mergeable=True,
                    head={'ref': 'work/a', 'sha': work, 'repo': {'full_name': 'owner/product'}}, base={'ref': 'main'})
            if path.startswith('/pulls/1/files?'): return [{'filename': 'src/new.py', 'previous_filename': 'src/old.py'}]
            if path.startswith('/compare/'): return {'merge_base_commit': {'sha': main}}
            if path.startswith('/git/commits/'): return {'tree': {'sha': sha('tree')}}
            if path.startswith('/git/trees/'): return dict(truncated=False, tree=[])
            raise AssertionError(path)
        api.call = call
        result = api.snapshot()
        self.assertTrue(result['complete'])
        self.assertEqual(result['document'], doc)
        self.assertEqual(result['prs'][0]['files'], ['src/new.py', 'src/old.py'])
        self.assertEqual(result['prs'][0]['merge_base_code'], result['base_code'])
        self.assertGreaterEqual(seen.count('/git/ref/heads/main'), 2)

    def test_registry_save_sends_exact_old_sha_and_safe_message(self):
        api = GitHub('owner/product', '')
        captured = []
        def call(method, path, data):
            captured.append((method, path, data))
            return {'content': {'sha': blob('next')}}
        api.call = call
        api.save(dict(repo='owner/product', registry_path='ACTIVE_WORK.md', expected_sha=sha('old'), document='next'))
        self.assertEqual(captured[0][2]['sha'], sha('old'))
        self.assertIn('[skip render]', captured[0][2]['message'])
        self.assertEqual(captured[0][2]['branch'], 'main')

    def test_registry_save_requires_confirmed_result_hash(self):
        api = GitHub('owner/product', '')
        api.call = lambda *a: {'content': {'sha': sha('wrong')}}
        with self.assertRaises(core.Refused) as e:
            api.save(dict(repo='owner/product', registry_path='ACTIVE_WORK.md', expected_sha=sha('old'), document='next'))
        self.assertEqual(e.exception.code, 'SAVE_UNCONFIRMED')

    def test_publish_preserves_parent_and_never_forces_ref(self):
        api = GitHub('owner/product', '')
        parent, child = sha('parent'), sha('child')
        heads = iter([parent, child])
        api.head = lambda branch: next(heads)
        api.commit = lambda value: {'tree': {'sha': sha('base-tree')}}
        captured = []
        def call(method, path, body):
            captured.append((method, path, body))
            return {'sha': child if path == '/git/commits' else sha('tree')}
        api.call = call
        self.assertEqual(api.publish('work/a', parent, {'src/a': 'content'}, 'fix: a'), child)
        self.assertEqual(captured[1][2]['parents'], [parent])
        self.assertIs(captured[-1][2]['force'], False)

    def test_merge_uses_expected_head_without_disabling_product_CI(self):
        api = GitHub('owner/product', '')
        captured = []
        api.call = lambda *args: captured.append(args) or {'merged': True}
        api.merge(12, sha('head'))
        payload = captured[0][2]
        self.assertEqual(payload['sha'], sha('head'))
        self.assertEqual(payload['merge_method'], 'merge')
        self.assertNotIn('skip', payload['commit_title'])

    def test_sync_posts_pinned_main_not_mutable_name(self):
        api = GitHub('owner/product', '')
        calls = []
        api.call = lambda *args: calls.append(args)
        api.sync('work/a', sha('main'))
        self.assertEqual(calls[0][1], '/merges')
        self.assertEqual(calls[0][2]['head'], sha('main'))

    def test_sync_parent_mismatch_rejected(self):
        api = GitHub('owner/product', '')
        api.commit = lambda h: {'parents': [{'sha': sha('unexpected')}, {'sha': sha('main')}]}
        proof = api.sync_proof(sha('old'), sha('main'), sha('child'))
        self.assertFalse(proof['verified'])

    def test_product_merge_rebase_or_squash_not_falsely_confirmed(self):
        api = GitHub('owner/product', '')
        api.call = lambda *a: dict(merged=True, merge_commit_sha=sha('squash'))
        api.commit = lambda s: {'parents': [{'sha': sha('one-parent')}]}
        with self.assertRaises(core.Refused) as e: api.merge_proof(1, sha('main'))
        self.assertEqual(e.exception.code, 'MERGE_METHOD_UNSUPPORTED')

    def test_network_failure_is_unknown_outcome_for_write(self):
        from urllib.error import URLError
        api = GitHub('owner/product', 'not-a-real-token')
        class Opener:
            def open(self, *a, **k): raise URLError('not logged')
        api._opener = Opener()
        with self.assertRaises(core.Refused) as e: api.call('PUT', '/contents/ACTIVE_WORK.md', {})
        self.assertEqual(e.exception.code, 'API_OUTCOME_UNKNOWN')


if __name__ == '__main__':
    unittest.main()
