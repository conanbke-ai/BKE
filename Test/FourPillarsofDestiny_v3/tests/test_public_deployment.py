from __future__ import annotations

import os
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

from app import _RATE_BUCKETS, _RATE_LOCK, _prune_rate_buckets, _safe_progress_summary, app
from config import SETTINGS
from services import birth_profile_from_dict
from storage import read_json, write_json


def test_health_check_and_security_headers_are_available():
    response = app.test_client().get('/healthz')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'status': 'ready'}
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']


def test_render_blueprint_uses_safe_public_defaults():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / 'Dockerfile').read_text(encoding='utf-8')
    blueprint = (root.parents[1] / 'render.yaml').read_text(encoding='utf-8')

    assert 'gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1' in dockerfile
    assert 'PUBLIC_DEPLOYMENT=1' in dockerfile
    assert 'PERSIST_USER_DATA=0' in dockerfile
    assert 'EXTERNAL_SOURCE_ENABLED=0' in dockerfile
    assert 'AI_ENABLED=0' in dockerfile
    assert 'BUILD_AUTO_MATCHES=0' in dockerfile
    assert 'rootDir: Test/FourPillarsofDestiny_v3' in blueprint
    assert 'healthCheckPath: /healthz' in blueprint
    assert 'plan: free' in blueprint


def test_blank_optional_state_paths_keep_project_defaults():
    script = r'''
from config import ROOT, SETTINGS

assert SETTINGS.state_dir == ROOT.resolve()
assert SETTINGS.data_dir == (ROOT / 'data').resolve()
assert SETTINGS.browser_profile_dir == (ROOT / '.browser-profile').resolve()
'''
    env = os.environ.copy()
    env.update({'STATE_DIR': '', 'DATA_DIR': '', 'BROWSER_PROFILE_DIR': ''})
    subprocess.run(
        [sys.executable, '-B', '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_progress_summary_discards_unknown_fields_and_clamps_sizes():
    summary = _safe_progress_summary({
        'build_matches': 'yes',
        'group_members': 999,
        'members': -10,
        'birth_year': 9999,
        'timing_profile': 'anything',
        'unexpected': 'x' * 5000,
    })

    assert summary == {
        'build_matches': True,
        'include_pair': False,
        'disable_timing_learning': False,
        'birth_year': 2100,
        'group_members': SETTINGS.max_group_members,
        'members': 0,
        'timing_profile': 'preview',
    }


def test_birth_profile_rejects_unbounded_name():
    with pytest.raises(ValueError, match='이름은 40자 이내'):
        birth_profile_from_dict({
            'name': '가' * 41,
            'gender': 'F',
            'calendar_type': 'solar',
            'year': 2000,
            'month': 1,
            'day': 1,
            'hour': 12,
            'minute': 0,
        })


def test_json_writes_are_atomic_and_leave_no_temporary_file(tmp_path: Path):
    target = tmp_path / 'cache' / 'result.json'
    write_json(target, {'ok': True, 'name': '배경은'})

    assert read_json(target) == {'ok': True, 'name': '배경은'}
    assert list(target.parent.glob('*.tmp')) == []


def test_rate_limit_bucket_cleanup_removes_expired_one_off_visitors():
    with _RATE_LOCK:
        _RATE_BUCKETS.clear()
        for index in range(4200):
            _RATE_BUCKETS[(f'198.51.100.{index}', 'api_initial')] = deque([1.0])
        _prune_rate_buckets(now=1000.0)
        assert not _RATE_BUCKETS


def test_public_mode_blocks_test_data_and_enforces_request_boundaries(tmp_path: Path):
    script = r'''
from pathlib import Path

from app import _client_identity, app
from forceteller import collect_many_facts
from models import BirthProfile
from storage import write_json

client = app.test_client()
secure_origin = {'Origin': 'https://saju.example'}

with app.test_request_context(
    '/',
    headers={'X-Forwarded-For': '203.0.113.25, 10.0.0.4'},
    environ_base={'REMOTE_ADDR': '10.0.0.5'},
):
    assert _client_identity() == '203.0.113.25'

assert client.get('/test', base_url='https://saju.example', environ_base={'REMOTE_ADDR': '127.0.0.1'}).status_code == 404
home = client.get('/', base_url='https://saju.example')
assert home.status_code == 200
assert '서버 파일에 저장하거나 외부 AI·원국 서비스로 전송하지 않습니다.' in home.get_data(as_text=True)
assert home.headers.get('Strict-Transport-Security', '').startswith('max-age=')

assert client.post('/api/progress/start', data='{}', content_type='text/plain', base_url='https://saju.example').status_code == 415
assert client.post('/api/progress/start', json={}, base_url='https://saju.example', headers={'Origin': 'https://evil.example'}).status_code == 403

for _ in range(12):
    response = client.post('/api/progress/start', json={}, base_url='https://saju.example', headers=secure_origin)
    assert response.status_code == 200
limited = client.post('/api/progress/start', json={}, base_url='https://saju.example', headers=secure_origin)
assert limited.status_code == 429
assert limited.headers.get('Retry-After')

oversized = client.post(
    '/api/initial',
    data='{"padding":"' + ('x' * 40000) + '"}',
    content_type='application/json',
    base_url='https://saju.example',
    headers=secure_origin,
)
assert oversized.status_code == 413

blocked_matches = client.post(
    '/api/initial',
    json={
        'profile': {
            'name': '공개 기능 확인', 'gender': 'F', 'calendar_type': 'solar',
            'year': 2000, 'month': 1, 'day': 2, 'hour': 12, 'minute': 0,
        },
        'build_matches': True,
    },
    base_url='https://saju.example',
    headers=secure_origin,
)
assert blocked_matches.status_code == 200
assert blocked_matches.get_json()['data']['request_options']['build_matches'] is False

target = Path(__import__('os').environ['DATA_DIR']) / 'must-not-exist.json'
write_json(target, {'private': True})
assert not target.exists()

facts = collect_many_facts([BirthProfile(
    name='공개 배포 확인', gender='F', calendar_type='solar',
    year=2098, month=2, day=3, hour=12, minute=0,
)])
assert len(facts) == 1
forceteller_root = Path(__import__('os').environ['DATA_DIR']) / 'forceteller'
assert forceteller_root.exists()
assert list(forceteller_root.iterdir()) == []
'''
    env = os.environ.copy()
    env.update({
        'PUBLIC_DEPLOYMENT': '1',
        'PERSIST_USER_DATA': '0',
        'EXTERNAL_SOURCE_ENABLED': '0',
        'AI_ENABLED': '0',
        'DEBUG': '0',
        'MAX_REQUEST_BYTES': '32768',
        'MAX_GROUP_MEMBERS': '3',
        'STATE_DIR': str(tmp_path),
        'DATA_DIR': str(tmp_path / 'data'),
        'BROWSER_PROFILE_DIR': str(tmp_path / 'browser-profile'),
    })

    completed = subprocess.run(
        [sys.executable, '-B', '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
