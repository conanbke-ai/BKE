from __future__ import annotations

import traceback
from datetime import datetime

from flask import Flask, abort, jsonify, render_template, request

from config import SETTINGS
from locations import COUNTRIES
from progress_tracker import (
    ProgressCancelled,
    cancel_job,
    create_job,
    estimate as estimate_progress,
    get_job,
)
from services import birth_profile_from_dict, group_analysis, initial_analysis, pair_analysis
from test_fixture import FULL_TEST_FIXTURE

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False


def _record_server_error(context: str, exc: Exception) -> None:
    """Keep technical details in the server log and never expose raw exceptions in the UI."""
    folder = SETTINGS.data_dir / 'errors'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'server_errors.log').open('a', encoding='utf-8') as fp:
        fp.write(f'\n[{datetime.now().isoformat(timespec="seconds")}] {context}\n')
        fp.write(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


def _friendly_error(context: str) -> str:
    if context == 'pair':
        return '두 사람의 자료를 확인하는 중 문제가 생겼습니다. 입력한 생년월일시를 확인한 뒤 다시 시도해 주세요.'
    if context == 'group':
        return '그룹 자료를 확인하는 중 문제가 생겼습니다. 구성원의 생년월일시를 확인한 뒤 다시 시도해 주세요.'
    return '분석 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.'


def _normalized_progress_kind(value: object) -> str:
    kind = str(value or 'initial')
    return kind if kind in {'initial', 'pair', 'group'} else 'initial'


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'y', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'n', 'off', ''}:
        return False
    return default


def _job_callback(job_id: str | None):
    job = get_job(job_id)
    if not job:
        return None

    def callback(stage: str, fraction: float, message: str) -> None:
        # update() checks cancellation and raises cooperatively inside long-running work.
        job.update(stage, fraction, message)

    return callback


@app.post('/api/progress/estimate')
def api_progress_estimate():
    data = request.get_json(silent=True) or {}
    kind = _normalized_progress_kind(data.get('kind'))
    return jsonify({'ok': True, 'data': estimate_progress(kind, data.get('summary') or {})})


@app.post('/api/progress/start')
def api_progress_start():
    data = request.get_json(silent=True) or {}
    kind = _normalized_progress_kind(data.get('kind'))
    job = create_job(kind, data.get('summary') or {})
    return jsonify({'ok': True, 'data': job.snapshot()})


@app.get('/api/progress/<job_id>')
def api_progress(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': '진행 정보를 찾지 못했습니다.'}), 404
    return jsonify({'ok': True, 'data': job.snapshot()})


@app.post('/api/progress/<job_id>/cancel')
def api_progress_cancel(job_id: str):
    job = cancel_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': '진행 정보를 찾지 못했습니다.'}), 404
    return jsonify({'ok': True, 'data': job.snapshot()})


@app.get('/')
def index():
    # 로컬 개발에서는 입력 화면에서 테스트 데이터를 즉시 불러올 수 있게 fixture를 함께 전달합니다.
    # 원격 사용자는 기존처럼 fixture를 전혀 받지 않습니다.
    fixture = FULL_TEST_FIXTURE if _is_local_request() else None
    return render_template('index.html', app_name=SETTINGS.app_name, test_mode=False, test_fixture=fixture)


def _is_local_request() -> bool:
    return (request.remote_addr or '') in {'127.0.0.1', '::1'}


@app.get('/test')
def test_screen():
    # 테스트 입력에는 실제 개발용 인적 정보가 들어 있으므로 localhost에서만 노출합니다.
    if not _is_local_request():
        abort(404)
    return render_template(
        'index.html',
        app_name=SETTINGS.app_name,
        test_mode=True,
        test_fixture=FULL_TEST_FIXTURE,
    )


@app.get('/api/config')
def config():
    return jsonify({
        'ok': True,
        'data': {
            'app_name': SETTINGS.app_name,
            'auto_match_top_n': SETTINGS.top_n,
            'countries': [{'code': code, 'name': name} for code, name in COUNTRIES],
        },
    })


@app.post('/api/initial')
def api_initial():
    data = request.get_json(force=True) or {}
    job = get_job(str(data.get('job_id') or ''))
    try:
        if job:
            job.ensure_active()
        profile = birth_profile_from_dict(data.get('profile') or {})
        result = initial_analysis(
            profile,
            force_ai=_as_bool(data.get('force_ai'), False),
            ai_cache_only=_as_bool(data.get('ai_cache_only'), False),
            build_matches=data.get('build_matches'),
            pair_request=data.get('pair_request'),
            group_request=data.get('group_request'),
            progress_callback=_job_callback(data.get('job_id')),
        )
        if job:
            job.complete('리포트 준비가 끝났어요.')
        return jsonify({'ok': True, 'data': result})
    except ProgressCancelled:
        if job:
            job.cancel()
        return jsonify({'ok': False, 'cancelled': True, 'error': '분석을 중단했어요.'}), 409
    except ValueError as exc:
        _record_server_error('initial-input', exc)
        message = '입력한 출생정보를 다시 확인해 주세요.'
        if job:
            job.fail(message)
        return jsonify({'ok': False, 'error': message, 'kind': 'validation'}), 422
    except Exception as exc:
        _record_server_error('initial', exc)
        message = '리포트를 만드는 과정에서 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.'
        if job:
            job.fail(message)
        return jsonify({'ok': False, 'error': message, 'kind': 'internal'}), 500


@app.post('/api/pair')
def api_pair():
    data = request.get_json(force=True) or {}
    job = get_job(str(data.get('job_id') or ''))
    try:
        if job:
            job.ensure_active()
        user = birth_profile_from_dict(data.get('user') or {}, default_name='나')
        target = birth_profile_from_dict(data.get('target') or {}, default_name='상대')
        mode = 'friend' if data.get('mode') == 'friend' else 'love'
        result = pair_analysis(
            user,
            target,
            mode,
            False,
            progress_callback=_job_callback(data.get('job_id')),
        )
        if job:
            job.update('finalize', 1.0, '궁합 화면을 정리했어요.')
            job.complete('1:1 궁합 분석이 끝났어요.')
        return jsonify({'ok': True, 'data': result})
    except ProgressCancelled:
        if job:
            job.cancel()
        return jsonify({'ok': False, 'cancelled': True, 'error': '분석을 중단했어요.'}), 409
    except ValueError as exc:
        _record_server_error('pair-input', exc)
        message = str(exc) or '입력한 생년월일시를 다시 확인해 주세요.'
        if job:
            job.fail(message)
        return jsonify({'ok': False, 'error': message, 'kind': 'validation'}), 422
    except Exception as exc:
        _record_server_error('pair', exc)
        message = _friendly_error('pair')
        if job:
            job.fail(message)
        return jsonify({'ok': False, 'error': message, 'kind': 'internal'}), 500


@app.post('/api/group')
def api_group():
    data = request.get_json(force=True) or {}
    job = get_job(str(data.get('job_id') or ''))
    try:
        if job:
            job.ensure_active()
        rows = data.get('members') or []
        if len(rows) < 2:
            return jsonify({'ok': False, 'error': '그룹 분석에는 최소 2명이 필요합니다.'}), 400
        profiles = [birth_profile_from_dict(row, default_name=f'멤버 {index + 1}') for index, row in enumerate(rows)]
        context = str(data.get('context') or 'friends')
        result = group_analysis(
            profiles,
            context=context,
            use_ai=False,
            progress_callback=_job_callback(data.get('job_id')),
        )
        if job:
            job.update('finalize', 1.0, '그룹 관계표를 정리했어요.')
            job.complete('그룹 분석이 끝났어요.')
        return jsonify({'ok': True, 'data': result})
    except ProgressCancelled:
        if job:
            job.cancel()
        return jsonify({'ok': False, 'cancelled': True, 'error': '분석을 중단했어요.'}), 409
    except ValueError as exc:
        _record_server_error('group-input', exc)
        message = str(exc) or '그룹 구성원의 생년월일시를 다시 확인해 주세요.'
        if job:
            job.fail(message)
        return jsonify({'ok': False, 'error': message, 'kind': 'validation'}), 422
    except Exception as exc:
        _record_server_error('group', exc)
        message = _friendly_error('group')
        if job:
            job.fail(message)
        return jsonify({'ok': False, 'error': message, 'kind': 'internal'}), 500


if __name__ == '__main__':
    app.run(host=SETTINGS.host, port=SETTINGS.port, debug=SETTINGS.debug, threaded=True)
