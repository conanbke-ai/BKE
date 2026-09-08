"""GitHub REST transport, bounded reads and non-force writes only.

No new service, hosted runner, package dependency, credential scraping or retries.
GH_TOKEN/GITHUB_TOKEN may be supplied by the developer's local environment.
Connected-tool sessions can use offline plans instead; they must never export
connector credentials into this process.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from urllib import error, parse, request

from .core import REGISTRY, REPO, Refused, branch_name, need


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, repo: str, token: str | None = None) -> None:
        need(REPO.fullmatch(repo), 'BAD_REPOSITORY')
        self.repo = repo
        self.root = 'https://api.github.com/repos/' + repo
        self._token = token if token is not None else os.environ.get('GH_TOKEN', os.environ.get('GITHUB_TOKEN', ''))
        self._opener = request.build_opener(NoRedirect())

    def call(self, method: str, path: str, data=None):
        need(path.startswith('/') and not path.startswith('//'),
             'BAD_API_PATH')
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                   'User-Agent': 'tori-work-guard/1'}
        if self._token:
            headers['Authorization'] = 'Bearer ' + self._token
        if method != 'GET':
            need(bool(self._token), 'TOKEN_REQUIRED')
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = request.Request(self.root + path, data=body, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=25) as response:
                raw = response.read(8_000_001)
                need(len(raw) <= 8_000_000, 'API_RESPONSE_TOO_LARGE')
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:
            # Do not print bodies/headers: they may contain private data. Never retry writes.
            code = 'CAS_CONFLICT' if exc.code in {409, 422} else f'HTTP_{exc.code}'
            raise Refused(code) from None
        except (error.URLError, TimeoutError, OSError, ValueError):
            raise Refused('API_OUTCOME_UNKNOWN' if method != 'GET' else 'API_READ_FAILED') from None

    def pages(self, path: str, maximum: int = 10_000) -> list:
        result = []
        for page in range(1, maximum // 100 + 2):
            sep = '&' if '?' in path else '?'
            chunk = self.call('GET', f'{path}{sep}per_page=100&page={page}')
            need(isinstance(chunk, list), 'BAD_API_RESPONSE')
            result.extend(chunk)
            need(len(result) < maximum, 'INCOMPLETE_PAGINATION')
            if len(chunk) < 100:
                return result
        raise Refused('INCOMPLETE_PAGINATION')

    def head(self, branch: str) -> str:
        name = parse.quote(branch_name(branch), safe='')
        return self.call('GET', '/git/ref/heads/' + name)['object']['sha']

    def commit(self, sha: str) -> dict:
        need(len(sha) == 40 and all(c in '0123456789abcdef' for c in sha), 'BAD_SHA')
        return self.call('GET', '/git/commits/' + sha)

    def code_fingerprint(self, sha: str) -> str:
        tree = self.call('GET', '/git/trees/' + self.commit(sha)['tree']['sha'])
        need(not tree.get('truncated'), 'INCOMPLETE_TREE')
        entries = [{k: e[k] for k in ('path', 'mode', 'type', 'sha')}
                   for e in tree['tree'] if e['path'] != REGISTRY]
        # Root subtree hashes cover all descendants. Only the coordination file is excluded.
        raw = json.dumps(sorted(entries, key=lambda x: x['path']), sort_keys=True, separators=(',', ':'))
        return hashlib.sha1(raw.encode()).hexdigest()

    def document(self, sha: str) -> tuple[str, str | None]:
        try:
            data = self.call('GET', f'/contents/{REGISTRY}?ref={sha}')
        except Refused as exc:
            if exc.code == 'HTTP_404':
                return '', None  # repo + main were already resolved; init still requires review
            raise
        need(data.get('encoding') == 'base64' and data.get('type') == 'file', 'REGISTRY_NOT_TEXT')
        try:
            return base64.b64decode(data['content']).decode('utf-8'), data['sha']
        except (ValueError, UnicodeError):
            raise Refused('REGISTRY_NOT_TEXT') from None

    def snapshot(self) -> dict:
        main = self.head('main')
        document, blob = self.document(main)
        branches = {x['name']: x['commit']['sha'] for x in self.pages('/branches')}
        need(branches.get('main') == main, 'SNAPSHOT_MOVED')
        prs = []
        for row in self.pages('/pulls?state=open', 1000):
            pr = self.call('GET', f'/pulls/{row["number"]}')
            need(pr['state'] == 'open' and pr['head']['repo']['full_name'].casefold() == self.repo.casefold(),
                 'FORK_OR_PR_CHANGED', 'manual reconciliation required')
            changed = self.pages(f'/pulls/{pr["number"]}/files', 3000)
            need(len(changed) == pr['changed_files'], 'PR_FILES_CHANGED')
            paths = {v['filename'] for v in changed}
            paths.update(v['previous_filename'] for v in changed if v.get('previous_filename'))
            need(branches.get(pr['head']['ref']) == pr['head']['sha'], 'PR_HEAD_MOVED')
            comparison = self.call('GET', f'/compare/{main}...{pr["head"]["sha"]}?per_page=1')
            merge_base_code = self.code_fingerprint(comparison['merge_base_commit']['sha'])
            prs.append(dict(number=pr['number'], branch=pr['head']['ref'], head=pr['head']['sha'],
                            base=pr['base']['ref'], files=sorted(paths), complete=True,
                            draft=pr['draft'], mergeable=pr['mergeable'], merge_base_code=merge_base_code))
        need(self.head('main') == main, 'SNAPSHOT_MOVED')
        return dict(repo=self.repo, main_head=main, base_code=self.code_fingerprint(main),
                    document=document, registry_sha=blob, branches=branches, prs=prs,
                    complete=True, observed_at=datetime.now(timezone.utc).isoformat())

    def save(self, plan: dict) -> dict:
        need(plan['repo'] == self.repo and plan['registry_path'] == REGISTRY, 'WRONG_REPOSITORY')
        # Contents API requires the exact old blob SHA. Stale writers never refresh and overwrite.
        body = dict(message='chore(coordination): work reservation checkpoint [skip ci] [skip render]',
                    branch='main', content=base64.b64encode(plan['document'].encode()).decode())
        if plan['expected_sha'] is not None:
            body['sha'] = plan['expected_sha']
        result = self.call('PUT', '/contents/' + REGISTRY, body)
        expected = hashlib.sha1(b'blob ' + str(len(plan['document'].encode())).encode() + b'\0' +
                                plan['document'].encode()).hexdigest()
        need(result['content']['sha'] == expected, 'SAVE_UNCONFIRMED')
        return result

    def create_branch(self, branch: str, sha: str) -> None:
        self.call('POST', '/git/refs', {'ref': 'refs/heads/' + branch_name(branch), 'sha': sha})

    def publish(self, branch: str, parent: str, files: dict[str, str], message: str) -> str:
        need(self.head(branch) == parent, 'HEAD_MOVED')
        tree = self.call('POST', '/git/trees', {
            'base_tree': self.commit(parent)['tree']['sha'],
            'tree': [dict(path=p, mode='100644', type='blob', content=c) for p, c in files.items()]})
        commit = self.call('POST', '/git/commits', {'message': message, 'tree': tree['sha'], 'parents': [parent]})
        # No force/reset/delete endpoint is exposed by this adapter.
        self.call('PATCH', '/git/refs/heads/' + parse.quote(branch, safe=''),
                  {'sha': commit['sha'], 'force': False})
        need(self.head(branch) == commit['sha'], 'WRITE_OUTCOME_UNKNOWN')
        return commit['sha']

    def write_proof(self, parent: str, head: str) -> dict:
        data = self.call('GET', f'/compare/{parent}...{head}?per_page=1')
        paths = {f['filename'] for f in data.get('files', [])}
        paths.update(f['previous_filename'] for f in data.get('files', []) if f.get('previous_filename'))
        # Compare files are capped at 300. Refuse the boundary rather than infer completeness.
        need(len(data.get('files', [])) < 300, 'INCOMPLETE_DIFF')
        parents = self.commit(head)['parents']
        return dict(base=parent, head=head, files=sorted(paths), complete=True,
                    fast_forward=data['status'] in {'ahead', 'identical'} and data['behind_by'] == 0,
                    direct_parent=parents[0]['sha'] if len(parents) == 1 else None)

    def merge(self, number: int, head: str) -> dict:
        return self.call('PUT', f'/pulls/{number}/merge',
                         {'sha': head, 'merge_method': 'merge',
                          'commit_title': f'Merge reviewed work #{number}'})

    def merge_proof(self, number: int, main: str) -> dict:
        pr = self.call('GET', f'/pulls/{number}')
        need(pr['merged'] is True, 'MERGE_NOT_CONFIRMED')
        sha = pr['merge_commit_sha']
        parents = self.commit(sha)['parents']
        need(len(parents) == 2, 'MERGE_METHOD_UNSUPPORTED', 'guard requires merge commit')
        ancestry = self.call('GET', f'/compare/{sha}...{main}?per_page=1')
        return dict(pr=number, merged=True, head=parents[1]['sha'], merge_sha=sha,
                    before_code=self.code_fingerprint(parents[0]['sha']),
                    after_code=self.code_fingerprint(sha),
                    in_main=ancestry['status'] in {'ahead', 'identical'} and ancestry['behind_by'] == 0)


    def sync(self, branch: str, main: str) -> None:
        self.call('POST', '/merges', {'base': branch_name(branch), 'head': main,
                                     'commit_message': 'Merge pinned main into reserved work branch'})

    def sync_proof(self, old_head: str, main: str, head: str) -> dict:
        parents = [p['sha'] for p in self.commit(head)['parents']]
        verified = parents == [old_head, main]
        if head == old_head:
            data = self.call('GET', f'/compare/{main}...{head}?per_page=1')
            verified = data['status'] in {'ahead', 'identical'} and data['behind_by'] == 0
        elif head == main:
            data = self.call('GET', f'/compare/{old_head}...{main}?per_page=1')
            verified = data['status'] in {'ahead', 'identical'} and data['behind_by'] == 0
        return dict(old_head=old_head, main=main, head=head, verified=verified)
