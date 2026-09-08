"""Orchestrate registry CAS + explicitly requested external effects.

Registry and product refs are not a distributed transaction. A crash/unknown
outcome leaves BRANCHING/WRITING/INTEGRATING locked for inspection, never unlocked
or blindly retried. Recovery uses the finish/abort commands and actual proofs.
"""
from __future__ import annotations

import uuid
from . import core


class Guard:
    def __init__(self, api) -> None:
        self.api = api

    def inspect(self) -> dict:
        snapshot = self.api.snapshot()
        _, state = core.decode(snapshot['document'])
        return dict(snapshot=snapshot, inventory_id=core.inventory_id(snapshot), state=state,
                    branch_count=len(snapshot['branches']), initialized=state is not None)

    def transition(self, q: dict) -> dict:
        return self._transition(q, self.api.snapshot())

    def _transition(self, q: dict, snapshot: dict) -> dict:
        _, state = core.decode(snapshot['document'])
        if q.get('action') == 'finish-write' and state:
            t = state['tasks'][q['task']]
            snapshot['write_proof'] = self.api.write_proof(t['head'], snapshot['branches'][t['branch']])
        if q.get('action') == 'finish-sync' and state:
            t = state['tasks'][q['task']]
            snapshot['sync_proof'] = self.api.sync_proof(t['head'], t['operation']['main'],
                                                         snapshot['branches'][t['branch']])
        if q.get('action') == 'merge-finish' and state:
            t = state['tasks'][q['task']]
            snapshot['merge_proof'] = self.api.merge_proof(t['pr'], snapshot['main_head'])
        result = core.accept(snapshot, q) if q['action'] == 'accept' else core.plan(snapshot, q)
        if result['mutation']:
            self.api.save(result)
        return result

    def _finish(self, original: dict, action: str, **extra) -> dict:
        snapshot = self.api.snapshot()
        _, state = core.decode(snapshot['document'])
        task = state['tasks'][original['task']]
        q = dict(action=action, task=original['task'], actor=original['actor'],
                    epoch=task['epoch'], revision=state['revision'],
                    request_id=uuid.uuid4().hex, **extra)
        return self._transition(q, snapshot)

    def create_branch(self, q: dict) -> dict:
        started = self.transition(dict(q, action='create-start'))
        core.need(not started.get('replay'), 'OPERATION_ALREADY_STARTED', 'inspect and finish/abort')
        task = started['state']['tasks'][q['task']]
        self.api.create_branch(task['branch'], task['base'])
        return self._finish(q, 'create-finish', operation=q['request_id'])

    def write(self, q: dict, files: dict[str, str], message: str) -> dict:
        core.need(isinstance(files, dict) and 0 < len(files) <= 64 and
                  all(isinstance(p, str) and isinstance(v, str) for p, v in files.items()), 'BAD_FILES')
        core.need(sum(len(v.encode()) for v in files.values()) <= 500_000, 'WRITE_TOO_LARGE')
        core.text(message)
        # No delete, shell, reset, force, or inferred branch-creation operation here.
        started = self.transition(dict(q, action='begin-write', paths=sorted(files)))
        core.need(not started.get('replay'), 'OPERATION_ALREADY_STARTED', 'inspect actual HEAD')
        task = started['state']['tasks'][q['task']]
        current = self.api.snapshot()
        core.check(current, dict(q, operation=q['request_id'], paths=sorted(files)))
        head = self.api.publish(task['branch'], task['head'], files, message)
        return self._finish(q, 'finish-write', operation=q['request_id'], new_head=head)

    def merge(self, q: dict) -> dict:
        core.text(q.get('approval'))  # Explicit integration request; never automatic from tests PASS.
        started = self.transition(dict(q, action='merge-start'))
        core.need(not started.get('replay'), 'OPERATION_ALREADY_STARTED', 'inspect actual PR')
        task = started['state']['tasks'][q['task']]
        lock = started['state']['integration']
        current = self.api.snapshot()
        _, state = core.decode(current['document'])
        core.need(state['integration'] == lock and current['base_code'] == lock['base_code'],
                  'BASE_CHANGED')
        pr = core._pr(task, current, task['pr'])
        core.need(pr['draft'] is False and pr['mergeable'] is True, 'PR_NOT_MERGEABLE')
        result = self.api.merge(task['pr'], task['head'])
        core.need(result.get('merged') is True, 'MERGE_NOT_CONFIRMED')
        return self._finish(q, 'merge-finish', operation=q['request_id'])


    def sync(self, q: dict) -> dict:
        started = self.transition(dict(q, action='begin-sync'))
        core.need(not started.get('replay'), 'OPERATION_ALREADY_STARTED', 'inspect actual HEAD')
        task = started['state']['tasks'][q['task']]
        current = self.api.snapshot()
        _, state = core.decode(current['document'])
        core.need(state['tasks'][q['task']]['operation'] == task['operation'] and
                  current['branches'][task['branch']] == task['head'], 'HEAD_MOVED')
        self.api.sync(task['branch'], task['operation']['main'])
        return self._finish(q, 'finish-sync', operation=q['request_id'])
