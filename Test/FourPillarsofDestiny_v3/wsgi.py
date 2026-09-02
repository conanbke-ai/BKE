from __future__ import annotations

import hmac
import os
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from urllib.parse import urlsplit

from flask import jsonify, redirect, render_template, request, session, url_for

from app import app
from config import SETTINGS


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return default if value is None else int(value)
    except (TypeError, ValueError):
        return default


_BETA_ENABLED = _env_bool('BETA_ACCESS_ENABLED', False)
_BETA_INVITE_CODE = str(os.getenv('BETA_INVITE_CODE') or '').strip()
_BETA_SECRET_KEY = str(os.getenv('SECRET_KEY') or '').strip()
_BETA_SESSION_DAYS = max(1, _env_int('BETA_SESSION_DAYS', 14))
_BETA_MAX_ATTEMPTS = max(3, _env_int('BETA_MAX_ATTEMPTS', 8))
_BETA_ATTEMPT_WINDOW_SECONDS = max(60, _env_int('BETA_ATTEMPT_WINDOW_SECONDS', 600))

if _BETA_ENABLED:
    if not _BETA_INVITE_CODE:
        raise RuntimeError('BETA_ACCESS_ENABLED=1이면 BETA_INVITE_CODE가 필요합니다.')
    if SETTINGS.public_deployment and len(_BETA_INVITE_CODE) < 12:
        raise RuntimeError('공개 베타 초대코드는 12자 이상으로 설정해 주세요.')
    if not _BETA_SECRET_KEY:
        raise RuntimeError('BETA_ACCESS_ENABLED=1이면 SECRET_KEY가 필요합니다.')

    app.secret_key = _BETA_SECRET_KEY
    app.permanent_session_lifetime = timedelta(days=_BETA_SESSION_DAYS)
    app.config.update(
        SESSION_COOKIE_NAME='untori_beta_access',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=bool(SETTINGS.public_deployment),
        SESSION_COOKIE_SAMESITE='Lax',
    )

_ATTEMPT_LOCK = threading.RLock()
_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)


def _identity() -> str:
    if SETTINGS.public_deployment:
        forwarded = str(request.headers.get('CF-Connecting-IP') or '').strip()
        if forwarded:
            return forwarded[:128]
    return str(request.remote_addr or 'unknown')[:128]


def _too_many_attempts(identity: str) -> tuple[bool, int]:
    now = time.monotonic()
    cutoff = now - _BETA_ATTEMPT_WINDOW_SECONDS
    with _ATTEMPT_LOCK:
        bucket = _ATTEMPTS[identity]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= _BETA_MAX_ATTEMPTS:
            retry_after = max(1, int(_BETA_ATTEMPT_WINDOW_SECONDS - (now - bucket[0])))
            return True, retry_after
        bucket.append(now)
        return False, 0


def _clear_attempts(identity: str) -> None:
    with _ATTEMPT_LOCK:
        _ATTEMPTS.pop(identity, None)


def _safe_next(value: str | None) -> str:
    target = str(value or '').strip()
    if not target:
        return '/'
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith('/') or target.startswith('//'):
        return '/'
    if target.startswith('/beta-access') or target.startswith('/beta-logout'):
        return '/'
    return target


def _has_beta_access() -> bool:
    return bool(session.get('beta_access_granted'))


@app.route('/beta-access', methods=['GET', 'POST'])
def beta_access():
    if not _BETA_ENABLED:
        return redirect('/')

    next_url = _safe_next(request.values.get('next'))
    if _has_beta_access():
        return redirect(next_url)

    error = None
    retry_after = None
    if request.method == 'POST':
        identity = _identity()
        limited, retry_after = _too_many_attempts(identity)
        if limited:
            error = '입력 횟수가 많아요. 잠시 뒤 다시 시도해 주세요.'
        else:
            supplied = str(request.form.get('invite_code') or '').strip()
            if supplied and hmac.compare_digest(supplied, _BETA_INVITE_CODE):
                _clear_attempts(identity)
                session.clear()
                session.permanent = True
                session['beta_access_granted'] = True
                session['beta_access_at'] = int(time.time())
                return redirect(next_url)
            error = '초대코드를 다시 확인해 주세요.'

    response = render_template(
        'beta_access.html',
        app_name=SETTINGS.app_name,
        error=error,
        next_url=next_url,
        session_days=_BETA_SESSION_DAYS,
    )
    status = 429 if retry_after else (403 if error else 200)
    return response, status, ({'Retry-After': str(retry_after)} if retry_after else {})


@app.get('/beta-logout')
def beta_logout():
    session.clear()
    return redirect(url_for('beta_access'))


@app.before_request
def require_beta_access():
    if not _BETA_ENABLED:
        return None

    path = request.path or '/'
    if path in {'/healthz', '/beta-access', '/beta-logout'} or path.startswith('/static/'):
        return None
    if _has_beta_access():
        return None

    if path.startswith('/api/'):
        return jsonify({
            'ok': False,
            'error': '현재 초대 베타 운영 중입니다. 초대코드 인증 후 이용해 주세요.',
            'kind': 'beta_access_required',
        }), 401

    return redirect(url_for('beta_access', next=_safe_next(request.full_path.rstrip('?'))))
