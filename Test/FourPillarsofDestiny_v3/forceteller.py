from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import time
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from bazi_engine import calculate_chart, derive_ten_gods
from config import SETTINGS
from constants import (
    BRANCHES,
    ELEMENTS,
    HIDDEN_STEMS,
    SPECIAL_STAR_NAMES,
    STEMS,
)
from models import BirthProfile, Chart, ForcetellerFacts
from storage import canonical_profile_identity, legacy_profile_key, profile_key, read_json, stable_hash, write_json

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
    PlaywrightTimeoutError = TimeoutError

SEL = {
    'name': '#name',
    'calendar': 'select[name="calendar"]',
    'birthday': '#birthday',
    'birthtime': '#birthtime',
    'time_unknown': 'input[name="mUnSure"]',
    'location_text': '#locationId',
    'location_value': 'input[type="hidden"][name="locationId"]',
}

ELEMENT_KO_TO_HANJA = {'목': '木', '화': '火', '토': '土', '금': '金', '수': '水'}
TEN_GOD_NAMES = ('비견', '겁재', '식신', '상관', '편재', '정재', '편관', '정관', '편인', '정인')
STRENGTH_LABELS = ('중화신약', '중화신강', '극신약', '극신강', '신약', '신강', '중화')


def _fill_masked(locator, value: str) -> None:
    locator.wait_for(state='visible', timeout=SETTINGS.browser_timeout_ms)
    locator.click()
    locator.fill(value)
    locator.press('Tab')
    if locator.input_value().strip() != value:
        locator.click()
        locator.press('Control+A')
        locator.type(value, delay=35)
        locator.press('Tab')
    actual = locator.input_value().strip()
    if actual != value:
        raise RuntimeError(f'입력값 반영 실패: 기대={value}, 실제={actual}')
    _dispatch_validation_events(locator)


def _set_gender(page, gender: str) -> None:
    selector = f'input[name="gender"][value="{gender}"]'
    radio = page.locator(selector).first
    radio.wait_for(state='attached', timeout=10000)
    if not radio.is_checked():
        label = page.locator(f'label:has({selector})').first
        try:
            if label.count():
                label.click(timeout=5000)
            else:
                radio.click(force=True)
        except Exception:
            radio.evaluate('(el) => el.click()')
    if not radio.is_checked():
        raise RuntimeError('성별 선택 실패')


def _dispatch_validation_events(locator) -> None:
    """SPA 폼의 내부 validation 상태가 DOM 값과 어긋나지 않도록 이벤트를 다시 전달한다."""
    try:
        locator.evaluate(
            """el => {
              for (const type of ['input', 'change', 'blur']) {
                el.dispatchEvent(new Event(type, {bubbles: true}));
              }
            }"""
        )
    except Exception:
        pass


def _refresh_form_validation(page) -> None:
    """입력값은 채워졌는데 버튼이 disabled인 SPA 상태를 한 번 동기화한다."""
    for selector in (
        SEL['name'], SEL['calendar'], SEL['birthday'], SEL['birthtime'],
        SEL['location_text'], SEL['location_value'], 'input[name="gender"]', SEL['time_unknown'],
    ):
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 4)):
                _dispatch_validation_events(loc.nth(i))
        except Exception:
            continue
    try:
        page.locator('body').click(position={'x': 12, 'y': 12}, force=True, timeout=1000)
    except Exception:
        pass
    page.wait_for_timeout(250)


def _form_state(page) -> str:
    """제출 실패 원인을 collector_error.txt에서 바로 구분할 수 있는 최소 진단값."""
    try:
        data = page.evaluate(
            """() => {
              const val = s => document.querySelector(s)?.value ?? '';
              const checked = s => !!document.querySelector(s)?.checked;
              return {
                url: location.href,
                name: val('#name'),
                birthday: val('#birthday'),
                birthtime: val('#birthtime'),
                calendar: val('select[name="calendar"]'),
                gender: document.querySelector('input[name="gender"]:checked')?.value ?? '',
                timeUnknown: checked('input[name="mUnSure"]'),
                locationText: val('#locationId'),
                locationId: val('input[type="hidden"][name="locationId"]')
              };
            }"""
        )
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return '{}'


def _wait_enabled(locator, *, page=None, stage: str = '제출', timeout_ms: int = 12000) -> None:
    end = time.time() + timeout_ms / 1000
    refreshed = False
    while time.time() < end:
        try:
            if locator.is_visible() and locator.is_enabled():
                return
        except Exception:
            pass
        if page is not None and not refreshed and time.time() > end - (timeout_ms / 1000) * 0.65:
            _refresh_form_validation(page)
            refreshed = True
        time.sleep(0.2)
    detail = _form_state(page) if page is not None else '{}'
    raise RuntimeError(f'{stage} 제출 버튼이 활성화되지 않았습니다. form_state={detail}')


def _inject_location(page, text: str, location_id: str) -> None:
    page.evaluate(
        """
        ({ text, id }) => {
          const visible = document.querySelector('#locationId');
          const hidden = document.querySelector('input[type="hidden"][name="locationId"]');
          function set(el, value) {
            if (!el) return;
            const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
            d.set.call(el, value);
            el.setAttribute('value', value);
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
          }
          set(visible, text); set(hidden, id);
          if (visible) visible.dispatchEvent(new Event('blur', {bubbles:true}));
          if (hidden) hidden.dispatchEvent(new Event('blur', {bubbles:true}));
        }
        """,
        {'text': text, 'id': location_id},
    )


def _select_location(page, profile: BirthProfile) -> tuple[str, str]:
    """출생 위치를 서비스 입력값에 맞춰 확인한다.

    - 대한민국은 사용자에게 시/군 입력을 받지 않고 대표 위치 ID를 사용한다.
    - 해외는 country + city를 검색 UI에 넣어 실제 위치 ID를 얻는다.
    - 해외 검색 실패 시 서울로 조용히 대체하지 않는다. 잘못된 시간 보정보다
      수집 실패로 처리하여 로컬 계산/주의 문구로 내려보내는 편이 안전하다.
    """
    if profile.country_code == 'KR':
        text = SETTINGS.default_location_text
        location_id = profile.location_id or SETTINGS.default_location_id
        _inject_location(page, text, location_id)
        return text, location_id

    if profile.location_id:
        _inject_location(page, profile.location, profile.location_id)
        return profile.location, profile.location_id

    city = (profile.city or '').strip()
    country = (profile.country or '').strip()
    if not city:
        raise RuntimeError('해외 출생 위치 확인에는 도시 정보가 필요합니다.')

    loc = page.locator(SEL['location_text']).first
    loc.click(timeout=5000)
    page.wait_for_timeout(400)

    candidates = [
        page.get_by_role('textbox', name=re.compile(r'도시|지역|검색|주소|국가')).last,
        page.locator('div[role="dialog"] input[type="text"]').last,
        page.locator('input[placeholder*="검색"], input[placeholder*="도시"], input[placeholder*="국가"]').last,
    ]
    search = None
    for candidate in candidates:
        try:
            if candidate.count() and candidate.is_visible():
                search = candidate
                break
        except Exception:
            continue
    if search is None:
        raise RuntimeError('출생 위치 검색창을 찾을 수 없습니다.')

    # 도시명만 검색하는 편이 사이트 검색 결과가 더 안정적이고,
    # 결과 선택 단계에서 국가명을 함께 확인해 동명 도시를 구분한다.
    search.fill(city)
    try:
        search.press('Enter')
    except Exception:
        pass
    page.wait_for_timeout(1400)

    option_texts = page.evaluate(
        """
        () => [...document.querySelectorAll('[role="option"], li, [role="dialog"] button')]
          .filter(el => {
            const s=getComputedStyle(el), r=el.getBoundingClientRect();
            return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
          })
          .map((el, i) => ({i, text:(el.innerText||el.textContent||'').trim()}))
          .filter(x => x.text)
          .slice(0, 120)
        """
    )

    city_lower = city.lower()
    country_lower = country.lower()
    chosen_text = ''
    # 우선 도시와 국가가 모두 들어간 결과, 그 다음 도시가 들어간 첫 결과를 고른다.
    for strict in (True, False):
        for row in option_texts:
            text = str(row.get('text', ''))
            low = text.lower()
            if city_lower not in low:
                continue
            if strict and country_lower and country_lower not in low:
                continue
            chosen_text = text
            break
        if chosen_text:
            break

    selected = False
    if chosen_text:
        selectors = [
            page.get_by_role('option', name=re.compile(re.escape(chosen_text))).first,
            page.locator('[role="option"]').filter(has_text=chosen_text).first,
            page.locator('li').filter(has_text=chosen_text).first,
            page.get_by_text(chosen_text, exact=False).first,
        ]
        for option in selectors:
            try:
                if option.count() and option.is_visible():
                    option.click(force=True, timeout=5000)
                    selected = True
                    break
            except Exception:
                continue

    if not selected:
        try:
            search.press('ArrowDown')
            search.press('Enter')
            selected = True
        except Exception:
            pass
    if not selected:
        raise RuntimeError(f'출생 위치를 찾지 못했습니다: {city}, {country}')

    page.wait_for_timeout(600)
    text = page.locator(SEL['location_text']).input_value().strip()
    hidden = page.locator(SEL['location_value']).input_value().strip()
    if not hidden or hidden == '0':
        raise RuntimeError(f'출생 위치 ID를 확인하지 못했습니다: {city}, {country}')
    return text or f'{city}, {country}', hidden


def _capture_json_responses(page):
    captured: list[dict[str, Any]] = []

    def on_response(response):
        try:
            if response.request.resource_type not in {'xhr', 'fetch'}:
                return
            if 'json' not in response.headers.get('content-type', '').lower():
                return
            captured.append({
                'url': response.url,
                'status': response.status,
                'payload': response.json(),
            })
        except Exception:
            return

    page.on('response', on_response)
    return captured, on_response


def _wait_for_result_sections(page, timeout_ms: int = 10000) -> None:
    """Wait for the independently rendered Forceteller result cards.

    The strength, guardian(useful element), special-stars, and daewoon areas are
    mounted asynchronously.  Capturing the first visible result is not sufficient:
    the saved HTML must contain the source cards that later parsers depend on.
    """
    core_timeout = max(2500, int(timeout_ms * 0.75))
    try:
        page.wait_for_function(
            """() => {
              const t = document.body?.innerText || '';
              const strength = !!document.querySelector('[data-test-id="singang"]') || t.includes('신강/신약') || t.includes('한 사주입니다');
              const guardian = !!document.querySelector('[data-test-id="guardian"]') || t.includes('용신');
              const daewoon = !!document.querySelector('[data-test-id="daeun-age"]') || !!document.querySelector('[data-test-id^="daeun"][data-test-id$="top"]') || t.includes('대운수');
              return strength && guardian && daewoon;
            }""",
            timeout=core_timeout,
        )
    except Exception:
        pass
    # 신살·길성 영역은 한 프레임 더 늦게 나타나는 경우가 있어 별도로 기다린다.
    try:
        page.wait_for_function(
            """() => {
              const t = document.body?.innerText || '';
              return t.includes('신살과 길성') || t.includes('도화살') || t.includes('월덕귀인');
            }""",
            timeout=max(1800, timeout_ms - core_timeout),
        )
    except Exception:
        pass
    try:
        page.wait_for_timeout(900)
    except Exception:
        pass

def _submit(page) -> list[dict[str, Any]]:
    first = page.get_by_role('button', name=re.compile(r'만세력\s*보러가기')).first
    first.wait_for(state='visible', timeout=15000)
    _wait_enabled(first, page=page, stage='입력 화면')
    first.click()
    try:
        page.wait_for_url(re.compile(r'/profile/confirm'), timeout=15000)
    except PlaywrightTimeoutError:
        pass
    captured, listener = _capture_json_responses(page)
    try:
        second = page.get_by_role('button', name=re.compile(r'만세력\s*보러가기')).first
        second.wait_for(state='visible', timeout=15000)
        _wait_enabled(second, page=page, stage='확인 화면')
        second.click()
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except PlaywrightTimeoutError:
            pass
        _wait_for_result_sections(page, timeout_ms=10000)
        return captured
    finally:
        page.remove_listener('response', listener)


def _normalize_key(value: Any) -> str:
    return re.sub(r'[^0-9a-z가-힣]', '', str(value).lower())


def _ganji_value(value: Any) -> str | None:
    if isinstance(value, str):
        compact = re.sub(r'\s+', '', value)
        m = re.search(r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])', compact)
        return ''.join(m.groups()) if m else None
    if isinstance(value, dict):
        n = {_normalize_key(k): v for k, v in value.items()}
        stems = ('stem', 'heavenlystem', '천간')
        branches = ('branch', 'earthlybranch', '지지')
        s = next((n[k] for k in stems if k in n), None)
        b = next((n[k] for k in branches if k in n), None)
        if isinstance(s, str) and isinstance(b, str) and s in STEMS and b in BRANCHES:
            return s + b
    return None


def _find_pillars(node: Any, require_hour: bool = True) -> dict[str, str] | None:
    aliases = {
        'year': {'yearpillar', 'yearganji', '생년', '연주', '년주'},
        'month': {'monthpillar', 'monthganji', '생월', '월주'},
        'day': {'daypillar', 'dayganji', '생일', '일주'},
        'hour': {'hourpillar', 'timepillar', 'hourganji', '생시', '시주'},
    }
    if isinstance(node, dict):
        n = [(_normalize_key(k), v) for k, v in node.items()]
        found: dict[str, str] = {}
        for p, keys in aliases.items():
            for k, v in n:
                if k in keys:
                    g = _ganji_value(v)
                    if g:
                        found[p] = g
                        break
        required = {'year', 'month', 'day', 'hour'} if require_hour else {'year', 'month', 'day'}
        if required.issubset(found.keys()):
            return found
        for v in node.values():
            result = _find_pillars(v, require_hour=require_hour)
            if result:
                return result
    elif isinstance(node, list):
        for v in node:
            result = _find_pillars(v, require_hour=require_hour)
            if result:
                return result
    return None


def _find_dict_with_keys(node: Any, wanted: set[str], key_mapper=lambda x: x) -> dict[str, float] | None:
    if isinstance(node, dict):
        mapped: dict[str, Any] = {}
        for k, v in node.items():
            mk = key_mapper(str(k))
            if mk:
                mapped[mk] = v
        if wanted.issubset(mapped.keys()):
            result: dict[str, float] = {}
            for k in wanted:
                try:
                    n = float(str(mapped[k]).replace('%', '').strip())
                except Exception:
                    break
                if not 0 <= n <= 100:
                    break
                result[k] = n
            if len(result) == len(wanted):
                return result
        for v in node.values():
            result = _find_dict_with_keys(v, wanted, key_mapper)
            if result:
                return result
    elif isinstance(node, list):
        for v in node:
            result = _find_dict_with_keys(v, wanted, key_mapper)
            if result:
                return result
    return None


def _element_key(k: str) -> str:
    k = k.strip()
    if k in ELEMENTS:
        return k
    for ko, hj in ELEMENT_KO_TO_HANJA.items():
        if ko == k or ko in k:
            return hj
    return ''


def _ten_god_key(k: str) -> str:
    compact = re.sub(r'\s+', '', k)
    for tg in TEN_GOD_NAMES:
        if tg == compact or tg in compact:
            return tg
    return ''


def _parse_element_percent(network: list[dict[str, Any]], text: str) -> tuple[dict[str, float], str]:
    for r in reversed(network):
        found = _find_dict_with_keys(r.get('payload'), set(ELEMENTS), _element_key)
        if found:
            return {e: round(found[e], 1) for e in ELEMENTS}, 'network_json'

    found_text: dict[str, float] = {}
    for ko, hj in ELEMENT_KO_TO_HANJA.items():
        matches = re.findall(rf'{ko}\s*([0-9]+(?:\.[0-9]+)?)\s*%', text)
        if matches:
            found_text[hj] = float(matches[0])
    if len(found_text) == 5:
        return found_text, 'visible_text'
    return {}, ''


def _parse_ten_gods(network: list[dict[str, Any]], text: str, fallback: dict[str, float]) -> tuple[dict[str, float], str]:
    wanted = set(TEN_GOD_NAMES)
    for r in reversed(network):
        found = _find_dict_with_keys(r.get('payload'), wanted, _ten_god_key)
        if found:
            return {k: round(v, 1) for k, v in found.items()}, 'network_json'
    parsed: dict[str, float] = {}
    for tg in TEN_GOD_NAMES:
        m = re.search(rf'{tg}\s*([0-9]+(?:\.[0-9]+)?)\s*%', text)
        if m:
            parsed[tg] = float(m.group(1))
    if len(parsed) >= 5:
        return parsed, 'visible_text'
    return fallback, 'local_hidden_stem_fallback'


def _walk_key_values(node: Any, tokens: tuple[str, ...]) -> list[Any]:
    result: list[Any] = []
    if isinstance(node, dict):
        for k, v in node.items():
            nk = _normalize_key(k)
            if any(token in nk for token in tokens):
                result.append(v)
            result.extend(_walk_key_values(v, tokens))
    elif isinstance(node, list):
        for value in node:
            result.extend(_walk_key_values(value, tokens))
    return result


def _parse_strength(network: list[dict[str, Any]], text: str, html_text: str = '') -> tuple[str, float | None]:
    """포스텔러에 명시된 신강·신약 판정을 최대한 직접적으로 읽는다.

    포스텔러 결과 페이지는 판정값을 ``data-test-id="singang"`` 영역 안의
    ``...님은 <b>신강</b>한 사주입니다`` 형태로 렌더링한다. 태그를 제거한
    텍스트뿐 아니라 원본 HTML에서도 직접 읽어, 캐시된 HTML의 공백/태그 형태가
    달라져도 판정이 사라지지 않게 한다.
    """
    label = ''
    index = None
    labels = '|'.join(map(re.escape, STRENGTH_LABELS))
    raw_html = html_text or ''

    # 1) 실제 singang 카드의 원본 HTML을 최우선으로 읽는다.
    marker = re.search(r'data-test-id=["\']singang["\']', raw_html, re.I)
    if marker:
        tail = raw_html[marker.start(): marker.start() + 9000]
        # <b>신강</b>, <strong>중화신강</strong> 등 태그가 끼어 있어도 허용.
        m_html = re.search(
            rf'님은\s*(?:<[^>]+>\s*)*({labels})(?:\s*</[^>]+>)*\s*한\s*사주',
            tail,
            re.I,
        )
        if m_html:
            label = m_html.group(1)
        plain = html_lib.unescape(re.sub(r'<[^>]+>', ' ', tail))
        plain = re.sub(r'\s+', ' ', plain)
        if not label:
            m = re.search(rf'님은\s*({labels})\s*한\s*사주', plain)
            if m:
                label = m.group(1)
        # 포스텔러가 명시적인 별도 지수를 제공하는 경우에만 숫자를 사용한다.
        m_idx = re.search(r'신강\s*/\s*신약\s*지수\s*[:：]?\s*(-?[0-9]+(?:\.[0-9]+)?)(?!\s*%)', plain)
        if m_idx:
            try:
                index = float(m_idx.group(1))
            except Exception:
                index = None

    # 2) 네트워크 JSON에 판정 라벨이 있으면 사용한다.
    if not label:
        for response in reversed(network):
            values = _walk_key_values(
                response.get('payload'),
                ('strengthlabel', 'strength_label', 'singanglabel', 'sinyaklabel', '신강신약'),
            )
            for value in values:
                raw = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                for candidate in STRENGTH_LABELS:
                    if candidate in raw:
                        label = candidate
                        break
                if label:
                    break
            if label:
                break

    # 3) 저장된 body text에서도 판정 문장을 다시 찾는다.
    compact = re.sub(r'\s+', ' ', text or '')
    if not label:
        m = re.search(rf'님은\s*({labels})\s*한\s*사주', compact)
        if m:
            label = m.group(1)
    if not label:
        idx = compact.find('신강/신약지수')
        region = compact[idx:idx + 2200] if idx >= 0 else compact[:2200]
        for candidate in STRENGTH_LABELS:
            if re.search(rf'(?<![가-힣]){re.escape(candidate)}(?![가-힣])', region):
                label = candidate
                break
    return label, index

def _parse_strength_factors(html_text: str, text: str = '') -> dict[str, bool | None]:
    """포스텔러 신강/신약 카드의 득령·득지·득시·득세 yes/no를 읽는다.

    이 값은 사용자 본문을 복잡하게 만들기 위한 것이 아니라, 신강·신약 판정이
    실제 포스텔러 카드에서 읽힌 것인지 검증하고 상세 근거에서만 보여주기 위한
    보조 데이터다.
    """
    factors = ('득령', '득지', '득시', '득세')
    result: dict[str, bool | None] = {}
    raw = html_text or ''
    marker = re.search(r'data-test-id=["\']singang["\']', raw, re.I)
    segment = raw[marker.start(): marker.start() + 12000] if marker else raw
    for name in factors:
        m = re.search(
            rf'{re.escape(name)}.*?(?:src=["\'][^"\']*icon_(yes|no)\.svg["\']|alt=["\']{re.escape(name)}["\'])',
            segment,
            re.I | re.S,
        )
        if m and m.group(1):
            result[name] = m.group(1).lower() == 'yes'
        elif name in (text or ''):
            result[name] = None
    return result


def _parse_useful_element_detail(text: str, html_text: str = '') -> str:
    raw = html_text or ''
    marker = re.search(r'data-test-id=["\']guardian["\']', raw, re.I)
    if marker:
        tail = raw[marker.start(): marker.start() + 3500]
        plain = html_lib.unescape(re.sub(r'<[^>]+>', ' ', tail))
        plain = re.sub(r'\s+', ' ', plain).strip()
        m = re.search(r'([목화토금수])\s*[\(（]([^\)）]{1,30}용신[^\)）]*)[\)）]', plain)
        if m:
            return f'{m.group(1)}({m.group(2)})'
    plain = re.sub(r'\s+', ' ', text or '')
    for m in re.finditer(r'용신', plain):
        region = plain[max(0, m.start()-120):m.end()+120]
        hit = re.search(r'([목화토금수])\s*[\(（]([^\)）]{1,30}용신[^\)）]*)[\)）]', region)
        if hit:
            return f'{hit.group(1)}({hit.group(2)})'
    return ''


def _extract_elements_from_value(value: Any) -> list[str]:
    raw = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    result: list[str] = []
    for ko, hj in ELEMENT_KO_TO_HANJA.items():
        if ko in raw and hj not in result:
            result.append(hj)
    for hj in ELEMENTS:
        if hj in raw and hj not in result:
            result.append(hj)
    return result


def _parse_useful_elements(network: list[dict[str, Any]], text: str, html_text: str = '') -> list[str]:
    # 실제 화면의 guardian 카드가 가장 직접적인 출처다.
    raw_html = html_text or ''
    marker = re.search(r'data-test-id=["\']guardian["\']', raw_html, re.I)
    if marker:
        tail = raw_html[marker.start(): marker.start() + 4000]
        plain = html_lib.unescape(re.sub(r'<[^>]+>', ' ', tail))
        result: list[str] = []
        for ko, hj in ELEMENT_KO_TO_HANJA.items():
            if re.search(rf'{ko}\s*[\(（][^\)）]{{0,30}}용신', plain) and hj not in result:
                result.append(hj)
        if result:
            return result[:3]

    for response in reversed(network):
        values = _walk_key_values(response.get('payload'), ('yongsin', 'useful', '용신'))
        result: list[str] = []
        for value in values:
            for element in _extract_elements_from_value(value):
                if element not in result:
                    result.append(element)
        if result:
            return result[:3]

    # 포스텔러 화면은 '화(억부용신)'처럼 원소가 '용신'보다 앞에 표시될 수 있다.
    raw = text or ''
    result: list[str] = []
    for m in re.finditer(r'용신', raw):
        region = raw[max(0, m.start() - 120):m.end() + 120]
        for ko, hj in ELEMENT_KO_TO_HANJA.items():
            if re.search(rf'{ko}\s*[\(（]?[^\n\r,]{{0,18}}용신|용신[^\n\r,]{{0,18}}{ko}', region) and hj not in result:
                result.append(hj)
        for hj in ELEMENTS:
            if hj in region and hj not in result:
                result.append(hj)
    return result[:3]

_STAR_TOKEN_RE = re.compile(r'(?<![가-힣])([가-힣]{1,8}(?:귀인|대살|살|성))(?![가-힣])')
_STAR_GENERIC_EXCLUDES = {
    '신살', '길성', '운성', '십이운성', '신강신약', '중심기운',
}

def _extract_star_names(value: str) -> list[str]:
    """Extract star names without depending on a fixed allow-list.

    The result page contains more star names than the app's historical constant list.
    Treating the constant list as the schema silently dropped valid rows, so the parser now
    recognizes the star-name shape first and uses the known list only as a supplement.
    """
    raw = html_lib.unescape(re.sub(r'<[^>]+>', '\n', value or ''))
    found: list[str] = []
    for m in _STAR_TOKEN_RE.finditer(raw):
        name = re.sub(r'\s+', '', m.group(1))
        if name in _STAR_GENERIC_EXCLUDES or len(name) > 10:
            continue
        if name not in found:
            found.append(name)
    if '암록' in raw and '암록' not in found:
        found.append('암록')
    for name in SPECIAL_STAR_NAMES:
        if name in raw and name not in found:
            found.append(name)
    return found

def _parse_special_stars(text: str) -> list[str]:
    """Parse every visible 신살·길성 name, preserving page order when possible."""
    raw = text or ''
    start = raw.find('신살과 길성')
    region = raw[start + len('신살과 길성'):] if start >= 0 else raw
    cuts = [i for marker in ('오행과 십성 분석', '신강/신약지수', '나의 오행', '대운수', '대운') if (i := region.find(marker)) >= 0]
    if cuts:
        region = region[:min(cuts)]
    found = _extract_star_names(region)
    # A few layouts repeat a star only in hidden/accessibility text outside the visible region.
    for name in _extract_star_names(raw):
        if name not in found:
            found.append(name)
    return found[:60]

def _parse_special_star_positions(text: str, html_text: str = '') -> dict[str, list[str]]:
    """신살·길성 표에서 시주→일주→월주→연주별 위치를 읽는다."""
    labels = [('생시', '시주'), ('생일', '일주'), ('생월', '월주'), ('생년', '연주')]
    result: dict[str, list[str]] = {}

    # HTML의 실제 열 순서를 우선 사용한다. 각 열은 다음 열 시작 전까지로 자른다.
    raw_html = html_text or ''
    if raw_html:
        html_start = raw_html.find('신살과 길성')
        if html_start >= 0:
            html_end = raw_html.find('오행과 십성 분석', html_start)
            raw_html = raw_html[html_start: html_end if html_end > html_start else len(raw_html)]
        starts: list[tuple[int, str]] = []
        for marker, label in labels:
            # 태그 안쪽 텍스트로 나타나는 첫 열 제목을 찾는다.
            hit = re.search(rf'>\s*{re.escape(marker)}\s*<', raw_html)
            if hit:
                starts.append((hit.start(), label))
        starts.sort()
        for i, (start, label) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else min(len(raw_html), start + 10000)
            segment = html_lib.unescape(re.sub(r'<[^>]+>', '\n', raw_html[start:end]))
            hits = _extract_star_names(segment)
            if hits:
                result[label] = hits
        if result:
            return result

    raw = text or ''
    start = raw.find('신살과 길성')
    region = raw[start:] if start >= 0 else raw
    end = region.find('오행과 십성 분석')
    if end >= 0:
        region = region[:end]
    for idx, (marker, label) in enumerate(labels):
        pos = region.find(marker)
        if pos < 0:
            continue
        next_positions = [region.find(next_marker, pos + len(marker)) for next_marker, _ in labels[idx + 1:]]
        next_positions = [x for x in next_positions if x >= 0]
        segment = region[pos + len(marker): min(next_positions) if next_positions else len(region)]
        hits = _extract_star_names(segment)
        if hits:
            result[label] = hits
    return result

def _parse_daewoon(text: str, html_text: str = '') -> list[dict[str, Any]]:
    """포스텔러의 실제 ``daeunNtop / daeunNbottom`` DOM을 같은 인덱스로 묶는다.

    상단 카드에는 시작 나이·십성·천간, 하단 카드에는 십이운성·십성·지지가
    따로 렌더링되므로, 화면 순서를 추측하지 않고 data-test-id의 N을 키로 합친다.
    """
    raw_html = html_text or ''
    result: list[dict[str, Any]] = []

    def block_for(idx: int, side: str) -> str:
        pat = re.compile(rf'data-test-id=["\']daeun{idx}{side}["\']', re.I)
        hit = pat.search(raw_html)
        if not hit:
            return ''
        # 같은 side의 다음 카드 또는 반대 side 첫 카드 전까지만 잘라낸다.
        next_hits = []
        for j in range(idx + 1, 13):
            h = re.search(rf'data-test-id=["\']daeun{j}{side}["\']', raw_html[hit.end():], re.I)
            if h:
                next_hits.append(hit.end() + h.start())
                break
        other = re.search(r'data-test-id=["\']daeun\d+(?:top|bottom)["\']', raw_html[hit.end():], re.I)
        if other:
            next_hits.append(hit.end() + other.start())
        end = min(next_hits) if next_hits else min(len(raw_html), hit.start() + 5000)
        start = raw_html.rfind('<div', 0, hit.start())
        if start < 0:
            start = hit.start()
        plain = html_lib.unescape(re.sub(r'<[^>]+>', ' ', raw_html[start:end]))
        return re.sub(r'\s+', ' ', plain).strip()

    for idx in range(12):
        top = block_for(idx, 'top')
        bottom = block_for(idx, 'bottom')
        if not top and not bottom:
            continue
        age_m = re.search(r'(?<!\d)(\d{1,3})(?!\d)', top)
        stem_m = re.search(r'[甲乙丙丁戊己庚辛壬癸]', top)
        top_tg = re.search(r'(비견|겁재|식신|상관|편재|정재|편관|정관|편인|정인)', top)
        branch_m = re.search(r'[子丑寅卯辰巳午未申酉戌亥]', bottom)
        bottom_tg = re.search(r'(비견|겁재|식신|상관|편재|정재|편관|정관|편인|정인)', bottom)
        stage_m = re.search(r'(장생|목욕|관대|건록|제왕|쇠|병|사|묘|절|태|양)', bottom)
        if not age_m or not stem_m or not branch_m:
            continue
        age = int(age_m.group(1))
        if not 0 <= age <= 120:
            continue
        row = {
            'age': age,
            'ten_god': top_tg.group(1) if top_tg else '',
            'stem': stem_m.group(0),
            'branch': branch_m.group(0),
            'branch_ten_god': bottom_tg.group(1) if bottom_tg else '',
            'twelve_stage': stage_m.group(1) if stage_m else '',
        }
        row['pillar'] = row['stem'] + row['branch']
        result.append(row)
    if len(result) >= 3:
        return sorted(result, key=lambda r: int(r.get('age', 999)))[:12]

    # 텍스트 fallback: 구조화 HTML이 없을 때만 보조적으로 사용한다.
    raw = text or ''
    start = raw.find('대운')
    if start < 0:
        return []
    region = raw[start:]
    end_candidates = [i for marker in ('연운', '세운', '월운', '일운') if (i := region.find(marker, 2)) > 0]
    if end_candidates:
        region = region[:min(end_candidates)]
    tg = r'(비견|겁재|식신|상관|편재|정재|편관|정관|편인|정인)'
    stems: list[dict[str, Any]] = []
    for m in re.finditer(rf'(?<!\d)(\d{{1,3}})\s*(?:세)?\s*{tg}.*?([甲乙丙丁戊己庚辛壬癸])', region, re.S):
        age = int(m.group(1))
        if 0 <= age <= 120:
            stems.append({'age': age, 'ten_god': m.group(2), 'stem': m.group(3)})
    stages = r'(장생|목욕|관대|건록|제왕|쇠|병|사|묘|절|태|양)'
    branches: list[dict[str, str]] = []
    for m in re.finditer(rf'{stages}\s*{tg}.*?([子丑寅卯辰巳午未申酉戌亥])', region, re.S):
        branches.append({'twelve_stage': m.group(1), 'branch_ten_god': m.group(2), 'branch': m.group(3)})
    fallback: list[dict[str, Any]] = []
    for idx, item in enumerate(stems[:12]):
        row = dict(item)
        if idx < len(branches):
            row.update(branches[idx])
            row['pillar'] = row['stem'] + row['branch']
        fallback.append(row)
    return fallback

def _parse_pillars_from_html(html_text: str, require_hour: bool = True) -> dict[str, str] | None:
    """Recover the four pillars directly from the rendered Forceteller result.

    Cached network responses are not guaranteed to contain the chart JSON.  The
    rendered '신살과 길성' grid, however, repeats each pillar as 생시/생일/생월/생년.
    Reading those columns lets a later parser revision keep Forceteller as the chart
    source instead of silently falling back to a local calculation.
    """
    raw = html_text or ''
    start = raw.find('신살과 길성')
    if start < 0:
        return None
    end = raw.find('오행과 십성 분석', start)
    region = raw[start:end if end > start else min(len(raw), start + 30000)]
    labels = [('생시', 'hour'), ('생일', 'day'), ('생월', 'month'), ('생년', 'year')]
    hits: list[tuple[int, str]] = []
    for ko, key in labels:
        m = re.search(rf'>\s*{re.escape(ko)}\s*<', region)
        if m:
            hits.append((m.start(), key))
    hits.sort()
    found: dict[str, str] = {}
    for i, (pos, key) in enumerate(hits):
        next_pos = hits[i + 1][0] if i + 1 < len(hits) else len(region)
        plain = html_lib.unescape(re.sub(r'<[^>]+>', ' ', region[pos:next_pos]))
        stem_m = re.search(r'[甲乙丙丁戊己庚辛壬癸]', plain)
        branch_m = re.search(r'[子丑寅卯辰巳午未申酉戌亥]', plain[stem_m.end():] if stem_m else plain)
        if stem_m and branch_m:
            found[key] = stem_m.group(0) + branch_m.group(0)
    required = {'year', 'month', 'day'} | ({'hour'} if require_hour else set())
    if not required.issubset(found):
        return None
    if not require_hour:
        found['hour'] = ''
    return found


def parse_facts(profile: BirthProfile, text: str, html_text: str, network: list[dict[str, Any]], source_path: str = '') -> ForcetellerFacts:
    local_chart = calculate_chart(profile)
    warnings: list[str] = []
    html_plain = html_lib.unescape(re.sub(r'<[^>]+>', ' ', html_text or ''))
    combined_text = (text or '') + '\n' + re.sub(r'\s+', ' ', html_plain)
    html_multiline = html_lib.unescape(re.sub(r'<[^>]+>', '\n', html_text or ''))
    multiline_text = (text or '') + '\n' + re.sub(r'\n{2,}', '\n', html_multiline)

    parsed_pillars = None
    for response in reversed(network):
        parsed_pillars = _find_pillars(response.get('payload'), require_hour=profile.time_known)
        if parsed_pillars:
            break
    if not parsed_pillars:
        parsed_pillars = _parse_pillars_from_html(html_text, require_hour=profile.time_known)

    chart = local_chart
    if parsed_pillars:
        p = parsed_pillars
        hour_pillar = p.get('hour', '') if profile.time_known else ''
        parsed_pillars_list = [p['year'], p['month'], p['day']] + ([hour_pillar] if hour_pillar else [])
        parsed_chart = Chart(
            year_pillar=p['year'], month_pillar=p['month'], day_pillar=p['day'], hour_pillar=hour_pillar,
            day_master=p['day'][0], spouse_palace=p['day'][1],
            stems=[x[0] for x in parsed_pillars_list],
            branches=[x[1] for x in parsed_pillars_list],
            element_percent_local=local_chart.element_percent_local,
        )
        chart = parsed_chart
        if (chart.year_pillar, chart.month_pillar, chart.day_pillar, chart.hour_pillar) != (
            local_chart.year_pillar, local_chart.month_pillar, local_chart.day_pillar, local_chart.hour_pillar
        ):
            warnings.append('포스텔러 원국과 로컬 원국 계산이 달라 포스텔러 원국을 우선 사용했습니다.')

    element_percent, element_source = _parse_element_percent(network, combined_text)
    if not element_percent:
        element_percent = dict(local_chart.element_percent_local)
        element_source = 'local_fallback'
        warnings.append('포스텔러 오행 비율을 찾지 못해 로컬 8글자 단순 비율을 보조값으로 사용했습니다.')

    fallback_tg = derive_ten_gods(chart)
    ten_gods, tg_source = _parse_ten_gods(network, combined_text, fallback_tg)
    strength, strength_index = _parse_strength(network, combined_text, html_text)
    strength_factors = _parse_strength_factors(html_text, combined_text)
    useful = _parse_useful_elements(network, combined_text, html_text)
    useful_detail = _parse_useful_element_detail(combined_text, html_text)
    stars = _parse_special_stars(multiline_text + '\n' + combined_text)
    star_positions = _parse_special_star_positions(multiline_text, html_text)
    daewoon = _parse_daewoon(multiline_text, html_text)

    quality = 35
    if parsed_pillars: quality += 20
    if element_source != 'local_fallback': quality += 15
    if tg_source != 'local_hidden_stem_fallback': quality += 10
    if strength: quality += 10
    if useful: quality += 10
    quality = min(100, quality)

    return ForcetellerFacts(
        profile=profile,
        chart=chart,
        element_percent=element_percent,
        ten_gods=ten_gods,
        strength_label=strength,
        strength_index=strength_index,
        strength_factors=strength_factors,
        useful_elements=useful,
        useful_element_detail=useful_detail,
        hidden_stems={b: HIDDEN_STEMS[b] for b in chart.branches},
        special_stars=stars,
        special_star_positions=star_positions,
        daewoon=daewoon,
        source_quality=quality,
        source='forceteller' if quality >= 60 else 'forceteller_partial',
        warnings=warnings,
        raw_source_path=source_path,
    )


_LEGACY_FACT_ALIASES: dict[str, tuple[str, ...]] = {
    'element_percent': ('element_percent', 'elementPercent', 'five_elements', 'fiveElements'),
    'ten_gods': ('ten_gods', 'tenGods', 'ten_god_percent'),
    'strength_label': ('strength_label', 'strengthLabel', 'strength', 'singang', 'singang_label', 'sinyak_label', 'strength_type'),
    'strength_index': ('strength_index', 'strengthIndex', 'singang_index'),
    'strength_factors': ('strength_factors', 'strengthFactors', 'singang_factors'),
    'useful_elements': ('useful_elements', 'usefulElements', 'useful_element', 'yongsin', 'guardian', 'useful'),
    'useful_element_detail': ('useful_element_detail', 'usefulElementDetail', 'yongsin_detail', 'guardian_detail'),
    'hidden_stems': ('hidden_stems', 'hiddenStems'),
    'special_stars': ('special_stars', 'specialStars', 'sinsal', 'stars', 'gilsung', 'specialStar'),
    'special_star_positions': ('special_star_positions', 'specialStarPositions', 'star_positions', 'sinsal_positions'),
    'daewoon': ('daewoon', 'daeun', 'dae_un', 'luck_cycles', 'major_luck'),
}


def _legacy_value(data: dict[str, Any], key: str, default: Any = None) -> Any:
    """Read facts across all historical cache schemas.

    Old releases stored some values under chart, others under facts/natal/analysis, and used
    both snake_case and camelCase.  Treat schema migration as a read concern so the UI never
    loses already-paid/collected source data merely because a filename or field moved.
    """
    aliases = _LEGACY_FACT_ALIASES.get(key, (key,))
    containers: list[dict[str, Any]] = [data]
    for parent_key in ('chart', 'facts', 'natal', 'analysis', 'result', 'source_facts'):
        row = data.get(parent_key)
        if isinstance(row, dict):
            containers.append(row)
    for container in containers:
        for alias in aliases:
            value = container.get(alias)
            if value not in (None, '', [], {}):
                return value
    return default


def _normalize_useful_elements(value: Any) -> list[str]:
    result: list[str] = []
    for element in _extract_elements_from_value(value):
        if element in ELEMENTS and element not in result:
            result.append(element)
    return result[:3]



def _legacy_profile_mapping(value: Any) -> dict[str, Any] | None:
    """Normalize old profile manifests before cache identity matching.

    Several v2 manifests stored only birth_date/birth_time/gender plus data_dir.  Treating
    those as a modern BirthProfile produced year=0/month=0/day=0 and made a perfectly good
    paid Forceteller cache invisible to the current app.
    """
    if not isinstance(value, dict):
        return None
    # Legacy collectors often stored birth identity under metadata.condition rather than
    # metadata.profile.  Prefer explicit profile, then condition, then the object itself.
    nested = value.get('profile') if isinstance(value.get('profile'), dict) else None
    if nested is None and isinstance(value.get('condition'), dict):
        nested = value.get('condition')
    raw = dict(nested or value)
    date_text = str(raw.get('birth_date') or raw.get('birthday') or '').strip()
    if not (raw.get('year') and raw.get('month') and raw.get('day')) and date_text:
        digits = re.findall(r'\d+', date_text)
        if len(digits) >= 3:
            raw['year'], raw['month'], raw['day'] = map(int, digits[:3])
        else:
            compact = re.sub(r'\D', '', date_text)
            if len(compact) == 8:
                raw['year'], raw['month'], raw['day'] = int(compact[:4]), int(compact[4:6]), int(compact[6:8])
    time_text = str(raw.get('birth_time') or raw.get('birthtime') or '').strip()
    explicit_known = raw.get('time_known')
    if explicit_known is None:
        raw['time_known'] = bool(time_text and time_text.lower() not in {'unknown', 'none', '모름', '미상'})
    if raw.get('time_known') and ('hour' not in raw or 'minute' not in raw) and time_text:
        nums = re.findall(r'\d+', time_text)
        if nums:
            raw['hour'] = int(nums[0])
            raw['minute'] = int(nums[1]) if len(nums) > 1 else 0
    if not raw.get('time_known'):
        raw['hour'], raw['minute'] = 12, 0
    gender = str(raw.get('gender') or 'F').strip().upper()
    raw['gender'] = 'F' if gender in {'F', 'FEMALE', '여', '여성'} else 'M'
    raw['calendar_type'] = 'lunar' if str(raw.get('calendar_type') or raw.get('calendar') or 'solar').lower() in {'lunar', 'l', '음력'} else 'solar'
    raw.setdefault('is_leap_month', False)
    raw.setdefault('country_code', 'KR')
    raw.setdefault('country', '대한민국')
    raw.setdefault('city', '')
    # v2 candidate metadata used location_text/location_id inside condition.
    raw.setdefault('location', raw.get('location_text') or SETTINGS.default_location_text)
    raw.setdefault('location_id', raw.get('location_value') or raw.get('location_id') or SETTINGS.default_location_id)
    required = ('year', 'month', 'day')
    if not all(int(raw.get(k) or 0) > 0 for k in required):
        return None
    return {k: v for k, v in raw.items() if k in BirthProfile.__dataclass_fields__}


def _normalize_special_stars(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    result: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            text = str(row.get('name') or row.get('label') or row.get('title') or row.get('star') or '')
        else:
            text = str(row or '')
        # JSON caches often store a clean name without surrounding whitespace.
        clean = re.sub(r'\s+', '', text)
        candidates = _extract_star_names(text)
        if clean == '암록':
            candidates = ['암록'] + candidates
        elif clean and (clean.endswith(('귀인', '대살', '살', '성'))) and clean not in _STAR_GENERIC_EXCLUDES:
            candidates = [clean] + candidates
        for name in candidates:
            if name not in result:
                result.append(name)
    return result


def _normalize_star_positions(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    aliases = {
        '생시': '시주', '시': '시주', 'hour': '시주', 'hour_pillar': '시주', '시주': '시주',
        '생일': '일주', '일': '일주', 'day': '일주', 'day_pillar': '일주', '일주': '일주',
        '생월': '월주', '월': '월주', 'month': '월주', 'month_pillar': '월주', '월주': '월주',
        '생년': '연주', '년': '연주', 'year': '연주', 'year_pillar': '연주', '연주': '연주',
    }
    # New/current schema: {"시주": ["도화살", ...]}
    for raw_key, raw_rows in value.items():
        key = aliases.get(str(raw_key).strip(), '')
        if not key:
            continue
        names = _normalize_special_stars(raw_rows)
        if names:
            result.setdefault(key, [])
            for name in names:
                if name not in result[key]:
                    result[key].append(name)
    if result:
        return result
    # Some legacy exports inverted the mapping: {"도화살": ["시주", "일주"]}.
    for raw_star, raw_positions in value.items():
        star_names = _normalize_special_stars(raw_star)
        if not star_names:
            continue
        rows = raw_positions if isinstance(raw_positions, list) else [raw_positions]
        for raw_position in rows:
            position = aliases.get(str(raw_position).strip(), '')
            if not position:
                continue
            result.setdefault(position, [])
            for name in star_names:
                if name not in result[position]:
                    result[position].append(name)
    return result

def _clean_chart_dict(raw: dict[str, Any], element_percent: dict[str, float] | None = None) -> dict[str, Any]:
    allowed = {
        'year_pillar', 'month_pillar', 'day_pillar', 'hour_pillar', 'day_master',
        'spouse_palace', 'stems', 'branches', 'element_percent_local',
    }
    out = {k: v for k, v in (raw or {}).items() if k in allowed}
    out.setdefault('hour_pillar', '')
    out.setdefault('stems', [])
    out.setdefault('branches', [])
    out.setdefault('element_percent_local', dict(element_percent or {}))
    day = str(out.get('day_pillar') or '')
    if day and not out.get('day_master'):
        out['day_master'] = day[0]
    if len(day) >= 2 and not out.get('spouse_palace'):
        out['spouse_palace'] = day[1]
    return out


def _facts_from_dict(data: dict[str, Any]) -> ForcetellerFacts:
    profile_raw = dict(data.get('profile') or {})
    p = BirthProfile(**profile_raw)
    element_percent = _legacy_value(data, 'element_percent', {}) or _legacy_value(data, 'element_percent_local', {}) or {}
    chart_raw = dict(data.get('chart') or {})
    # v2 계열 cache는 chart.element_percent라는 이름을 쓴 경우가 있다.
    if not element_percent:
        element_percent = chart_raw.get('element_percent') or chart_raw.get('element_percent_local') or {}
    c = Chart(**_clean_chart_dict(chart_raw, element_percent))
    useful = _normalize_useful_elements(_legacy_value(data, 'useful_elements', []) or [])
    source = str(data.get('source') or data.get('chart_source') or data.get('chartSource') or 'cache')
    quality = int(data.get('source_quality', data.get('sourceQuality', 0)) or 0)
    legacy_forceteller = source == 'forceteller' or str(data.get('chart_source') or data.get('chartSource') or '').lower() == 'forceteller'
    if legacy_forceteller and quality < SETTINGS.min_verified_source_quality:
        # Old exported caches often omitted source_quality even though the manifest explicitly
        # records that the chart was collected from Forceteller. Core fields still have to pass
        # _cached_facts_usable before this cache becomes authoritative.
        quality = SETTINGS.min_verified_source_quality
        source = 'forceteller_legacy_cache'
    return ForcetellerFacts(
        profile=p, chart=c,
        element_percent=element_percent,
        ten_gods=_legacy_value(data, 'ten_gods', {}) or {},
        strength_label=str(_legacy_value(data, 'strength_label', '') or ''),
        strength_index=_legacy_value(data, 'strength_index', None),
        strength_factors=_legacy_value(data, 'strength_factors', {}) or {},
        useful_elements=list(useful),
        useful_element_detail=str(_legacy_value(data, 'useful_element_detail', '') or ''),
        hidden_stems=_legacy_value(data, 'hidden_stems', {}) or {},
        special_stars=_normalize_special_stars(_legacy_value(data, 'special_stars', []) or []),
        special_star_positions=_normalize_star_positions(_legacy_value(data, 'special_star_positions', {}) or {}),
        daewoon=_legacy_value(data, 'daewoon', []) or [],
        source_quality=quality,
        source=source,
        warnings=list(data.get('warnings', []) or []),
        raw_source_path=str(data.get('raw_source_path', '') or ''),
    )


def local_facts(profile: BirthProfile, warning: str = '') -> ForcetellerFacts:
    chart = calculate_chart(profile)
    return ForcetellerFacts(
        profile=profile,
        chart=chart,
        element_percent=dict(chart.element_percent_local),
        ten_gods=derive_ten_gods(chart),
        hidden_stems={b: HIDDEN_STEMS[b] for b in chart.branches},
        source_quality=35,
        source='local_fallback',
        warnings=[warning] if warning else [],
    )


def _friendly_collection_warning(kind: str = 'collection') -> str:
    if kind == 'browser':
        return '포스텔러 연결을 확인하지 못해 현재 결과는 로컬 만세력 계산을 기준으로 표시합니다. 다시 분석하면 포스텔러 확인을 재시도합니다.'
    return '포스텔러 상세 자료를 확인하지 못해 현재 결과는 로컬 만세력 계산을 기준으로 표시합니다. 다시 분석하면 포스텔러 확인을 재시도합니다.'


def _write_internal_error(folder: Path, exc: Exception) -> None:
    """브라우저/셀렉터 오류는 서비스 화면에 노출하지 않고 개발용 파일에만 남긴다."""
    try:
        (folder / 'collector_error.txt').write_text(
            f'{type(exc).__name__}: {exc}',
            encoding='utf-8',
        )
    except Exception:
        pass


def _collect_on_page(page, profile: BirthProfile, folder: Path) -> ForcetellerFacts:
    """같은 탭을 재사용하여 persistent context의 새 탭 생성 실패를 피한다."""
    page.goto(SETTINGS.forceteller_edit_url, wait_until='domcontentloaded', timeout=SETTINGS.browser_timeout_ms)
    page.locator(SEL['name']).wait_for(state='visible', timeout=SETTINGS.browser_timeout_ms)

    page.locator(SEL['name']).fill(profile.name or '분석대상')
    _set_gender(page, profile.gender)
    page.locator(SEL['calendar']).select_option('S' if profile.calendar_type == 'solar' else 'L')
    _fill_masked(page.locator(SEL['birthday']), f'{profile.year:04d}/{profile.month:02d}/{profile.day:02d}')
    unknown = page.locator(SEL['time_unknown'])
    if profile.time_known:
        if unknown.count() and unknown.is_checked():
            unknown.click(force=True)
        _fill_masked(page.locator(SEL['birthtime']), f'{profile.hour:02d}:{profile.minute:02d}')
    else:
        # 포스텔러 자체의 '생시 모름' 옵션을 사용한다. 임의의 12:00을 제출하지 않는다.
        if unknown.count() and not unknown.is_checked():
            try:
                label = page.locator('label:has(input[name="mUnSure"])').first
                if label.count():
                    label.click(force=True)
                else:
                    unknown.click(force=True)
            except Exception:
                unknown.evaluate('(el) => el.click()')
        if unknown.count() and not unknown.is_checked():
            raise RuntimeError('포스텔러 생시 모름 선택 실패')
    location_text, location_id = _select_location(page, profile)
    page.locator(SEL['name']).press('Tab')
    _refresh_form_validation(page)
    page.wait_for_timeout(SETTINGS.polite_delay_ms)

    network = _submit(page)
    _wait_for_result_sections(page, timeout_ms=12000)

    def snapshot_result() -> tuple[str, str, ForcetellerFacts]:
        body_text = page.locator('body').inner_text(timeout=15000)
        # #root.inner_html()보다 page.content()를 저장해야 data-test-id와 주변 DOM
        # 문맥이 통째로 남아 이후 파서 개선 때 재수집 없이 복구할 수 있다.
        full_html = page.content()
        parsed = parse_facts(profile, body_text, full_html, network, str(folder))
        return body_text, full_html, parsed

    text, rendered, facts = snapshot_result()
    # 동적 카드가 늦게 붙는 환경에서는 한 번 더 기다렸다가 원문을 새로 캡처한다.
    if not facts.strength_label or not facts.useful_elements or not facts.daewoon or not facts.special_stars:
        _wait_for_result_sections(page, timeout_ms=6000)
        page.wait_for_timeout(800)
        text2, rendered2, facts2 = snapshot_result()
        facts = _merge_missing_verified_fields(facts2, facts)
        if len(rendered2) >= len(rendered):
            text, rendered = text2, rendered2

    (folder / 'result.txt').write_text(text, encoding='utf-8')
    (folder / 'result.html').write_text(rendered, encoding='utf-8')
    write_json(folder / 'network.json', network)
    try:
        page.screenshot(path=str(folder / 'result.png'), full_page=True)
    except Exception:
        pass
    write_json(folder / 'metadata.json', {
        'profile': profile.as_dict(),
        'location_text': location_text,
        'location_id': location_id,
        'result_url': page.url,
        'parser_version': SETTINGS.parser_version,
    })
    write_json(folder / 'forceteller_facts.json', facts.as_dict())
    # 정상 수집 후 과거 오류 파일은 제거한다.
    try:
        (folder / 'collector_error.txt').unlink(missing_ok=True)
    except Exception:
        pass
    return facts


def _merge_missing_verified_fields(primary: ForcetellerFacts, previous: ForcetellerFacts | None) -> ForcetellerFacts:
    """재파싱/새 수집 과정에서 과거에 확인된 상세 필드가 사라지는 것을 막는다."""
    if previous is None:
        return primary
    if not primary.strength_label and previous.strength_label:
        primary.strength_label = previous.strength_label
        primary.strength_index = previous.strength_index
        primary.strength_factors = dict(previous.strength_factors or {})
    elif not primary.strength_factors and previous.strength_factors:
        primary.strength_factors = dict(previous.strength_factors)
    if not primary.useful_elements and previous.useful_elements:
        primary.useful_elements = list(previous.useful_elements)
    if not primary.useful_element_detail and previous.useful_element_detail:
        primary.useful_element_detail = previous.useful_element_detail
    if not primary.special_stars and previous.special_stars:
        primary.special_stars = list(previous.special_stars)
    if not primary.special_star_positions and previous.special_star_positions:
        primary.special_star_positions = dict(previous.special_star_positions)
    if not primary.daewoon and previous.daewoon:
        primary.daewoon = list(previous.daewoon)
    if previous.source_quality > primary.source_quality and str(previous.source).startswith('forceteller'):
        primary.source_quality = previous.source_quality
        if primary.source == 'forceteller_partial':
            primary.source = previous.source
    return primary


def _fallback_preserving_existing(profile: BirthProfile, folder: Path, warning: str) -> ForcetellerFacts:
    """일시적인 브라우저 실패가 이미 확인된 포스텔러 캐시를 덮어쓰지 않게 한다."""
    fallback = local_facts(profile, warning)
    existing = read_json(folder / 'forceteller_facts.json', {}) or {}
    if isinstance(existing, dict) and existing:
        try:
            prior = _facts_from_dict(existing)
            if prior.chart.day_pillar and prior.source_quality >= fallback.source_quality:
                prior.profile = profile
                if warning and warning not in prior.warnings:
                    prior.warnings.append(warning)
                return prior
        except Exception:
            pass
    return fallback


def _reparse_cached_source(profile: BirthProfile, folder: Path) -> ForcetellerFacts | None:
    """저장 원문을 현재 파서로 다시 읽되 불완전 결과로 기존 캐시를 덮지 않는다.

    파서 개선 중 가장 위험했던 경로는 result.html에 신강·용신·대운이 있는데도
    일시적인 재파싱 실패 결과를 forceteller_facts.json에 저장해 다음 실행부터 그
    빈 값을 정답처럼 쓰는 것이었다. 재파싱 결과가 원문과 모순되지 않을 때만
    authoritative cache로 승격한다.
    """
    text_path = folder / 'result.txt'
    html_path = folder / 'result.html'
    if not text_path.exists() and not html_path.exists():
        return None
    try:
        previous_obj = None
        previous_raw = read_json(folder / 'forceteller_facts.json', {}) or {}
        if isinstance(previous_raw, dict) and previous_raw:
            try:
                previous_obj = _facts_from_dict(previous_raw)
            except Exception:
                previous_obj = None
        text = text_path.read_text(encoding='utf-8', errors='ignore') if text_path.exists() else ''
        html_text = html_path.read_text(encoding='utf-8', errors='ignore') if html_path.exists() else ''
        network = read_json(folder / 'network.json', []) or []
        facts = parse_facts(profile, text, html_text, network, str(folder))
        facts = _merge_missing_verified_fields(facts, previous_obj)
        facts.profile = profile
        reparsed_data = facts.as_dict()
        authoritative = (
            _cached_facts_usable(reparsed_data, False)
            and not _cached_facts_need_reparse(reparsed_data, folder)
        )
        if authoritative:
            write_json(folder / 'forceteller_facts.json', reparsed_data)
            metadata = read_json(folder / 'metadata.json', {}) or {}
            metadata.update({
                'profile': profile.as_dict(),
                'parser_version': SETTINGS.parser_version,
                'reparse_status': 'complete',
                'reparse_parser_version': SETTINGS.parser_version,
            })
            write_json(folder / 'metadata.json', metadata)
        else:
            # 진단용으로만 남기고 기존 캐시는 보존한다. 다음 실제 분석에서 재수집 가능하다.
            write_json(folder / 'forceteller_facts.reparse_partial.json', reparsed_data)
            metadata = read_json(folder / 'metadata.json', {}) or {}
            metadata.update({
                'profile': profile.as_dict(),
                'reparse_status': 'partial',
                'reparse_parser_version': SETTINGS.parser_version,
            })
            write_json(folder / 'metadata.json', metadata)
        return facts
    except Exception as exc:
        _write_internal_error(folder, exc)
        return None


def _cached_facts_usable(data: dict[str, Any], force: bool) -> bool:
    """Return whether a saved external source can reproduce the current analysis.

    Network policy is strict cache-first: once an actual saved source yields the day pillar,
    optional enrichment gaps never cause an automatic external revisit. Missing 용신/신강/대운
    are handled conservatively and raw HTML may be reparsed locally. Only an explicit
    ``force=True`` caller is allowed to bypass an otherwise reusable source cache.
    """
    if force:
        return False
    source = str(data.get('source', ''))
    quality = int(data.get('source_quality', 0) or 0)
    chart = data.get('chart') or {}

    if source == 'local_fallback':
        return False

    source_backed = source.startswith('forceteller') or quality >= SETTINGS.min_verified_source_quality
    return bool(source_backed and str(chart.get('day_pillar') or '').strip())



def _historical_data_roots() -> list[Path]:
    """Data roots that may contain paid/collected facts from an older app revision.

    Upgrading FourPillarsofDestiny_v2 -> v3 previously left rich Forceteller facts in the
    sibling project, so the new project behaved as if the person had never been collected.
    Reuse is based on normalized birth identity, never on a display name.
    """
    # Search both the modern data tree and historical output/candidates trees.
    # v2 collectors saved paid candidate captures under <project>/output/candidates, so
    # scanning only data/ makes those existing results invisible and causes re-querying.
    roots: list[Path] = [SETTINGS.data_dir, SETTINGS.root / 'output']
    env_rows = [x.strip() for x in os.getenv('LEGACY_DATA_DIRS', '').split(os.pathsep) if x.strip()]
    roots.extend(Path(x).expanduser() for x in env_rows)
    parent = SETTINGS.root.parent
    try:
        for project in parent.glob('FourPillarsofDestiny*'):
            for candidate in (project / 'data', project / 'output'):
                if candidate.is_dir():
                    roots.append(candidate)
    except Exception:
        pass
    seen: set[str] = set()
    result: list[Path] = []
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            key = str(root.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(root)
    return result


@lru_cache(maxsize=1)
def _historical_cache_index() -> dict[str, tuple[str, ...]]:
    """Index every saved Forceteller profile under the current data folder.

    Past versions used data/forceteller, data/candidates and manifest files pointing to
    another cache folder. The same birth identity can therefore exist in several places.
    The index is deliberately based on birth facts rather than display name.
    """
    mapping: dict[str, set[str]] = {}

    def add(profile_raw: Any, folder: Path) -> None:
        normalized = _legacy_profile_mapping(profile_raw)
        if not normalized:
            return
        try:
            identity = stable_hash(canonical_profile_identity(normalized))
        except Exception:
            return
        if folder.exists() and folder.is_dir():
            mapping.setdefault(identity, set()).add(str(folder))

    roots = _historical_data_roots()
    manifests: list[Path] = []
    for root in roots:
        try:
            manifests.extend(root.rglob('forceteller_profile.json'))
        except Exception:
            continue
    for manifest in manifests:
        raw = read_json(manifest, {}) or {}
        if not isinstance(raw, dict):
            continue
        target = Path(str(raw.get('data_dir') or '')).expanduser() if raw.get('data_dir') else manifest.parent
        resolved_target = target if target.exists() else manifest.parent
        add(raw, resolved_target)
        add(raw, manifest.parent)
        # Some manifests keep profile facts at the top level rather than under profile.
        add(raw.get('profile'), resolved_target)
        add(raw.get('profile'), manifest.parent)

    facts_files: list[Path] = []
    for root in roots:
        try:
            facts_files.extend(root.rglob('forceteller_facts.json'))
        except Exception:
            continue
    for facts_file in facts_files:
        raw = read_json(facts_file, {}) or {}
        if isinstance(raw, dict):
            add(raw.get('profile'), facts_file.parent)

    metadata_files: list[Path] = []
    for root in roots:
        try:
            metadata_files.extend(root.rglob('metadata.json'))
        except Exception:
            continue
    for metadata_file in metadata_files:
        raw = read_json(metadata_file, {}) or {}
        if not isinstance(raw, dict):
            continue
        # Restrict generic metadata.json files to folders that look like a Forceteller source.
        folder = metadata_file.parent
        if not ((folder / 'result.html').exists() or (folder / 'result.txt').exists() or (folder / 'forceteller_facts.json').exists()):
            continue
        # Modern metadata stores profile; v2 candidate collectors store condition with
        # birth_date/birth_time/gender.  Index both without depending on display names.
        add(raw, folder)
        add(raw.get('profile'), folder)
        add(raw.get('condition'), folder)

    return {key: tuple(sorted(rows)) for key, rows in mapping.items()}


def refresh_historical_cache_index() -> None:
    _historical_cache_index.cache_clear()


def _profile_matches_identity(profile: BirthProfile, folder: Path) -> bool:
    wanted = canonical_profile_identity(profile.as_dict())
    for filename in ('metadata.json', 'forceteller_facts.json'):
        raw = read_json(folder / filename, {}) or {}
        if not isinstance(raw, dict):
            continue
        candidates = [raw, raw.get('profile'), raw.get('condition')]
        for candidate in candidates:
            old_profile = _legacy_profile_mapping(candidate)
            if old_profile and canonical_profile_identity(old_profile) == wanted:
                return True
    return False


def _matching_profile_cache_folders(profile: BirthProfile) -> list[Path]:
    """Return all old/new cache folders for the same normalized birth identity."""
    profile_dict = profile.as_dict()
    identity_key = stable_hash(canonical_profile_identity(profile_dict))
    candidates: list[Path] = [
        SETTINGS.forceteller_dir / profile_key(profile_dict),
        SETTINGS.forceteller_dir / legacy_profile_key(profile_dict),
    ]
    candidates.extend(Path(row) for row in _historical_cache_index().get(identity_key, ()))
    # Also inspect direct children because a cache can be created after the index was built.
    try:
        for folder in SETTINGS.forceteller_dir.iterdir():
            if folder.is_dir() and _profile_matches_identity(profile, folder):
                candidates.append(folder)
    except Exception:
        pass
    seen: set[str] = set()
    result: list[Path] = []
    for folder in candidates:
        try:
            key = str(folder.resolve()) if folder.exists() else str(folder)
        except Exception:
            key = str(folder)
        if key in seen:
            continue
        seen.add(key)
        if folder.exists() and folder.is_dir():
            result.append(folder)
    return result


def _facts_completeness_score(facts: ForcetellerFacts, folder: Path) -> int:
    score = int(facts.source_quality or 0)
    if str(facts.source).startswith('forceteller'):
        score += 80
    if facts.chart.day_pillar:
        score += 25
    if facts.strength_label:
        score += 28
    if facts.useful_elements:
        score += 28
    if facts.special_stars:
        score += 18
    if facts.special_star_positions:
        score += 10
    if facts.daewoon:
        score += 35
    if (folder / 'result.html').exists():
        score += 8
    if (folder / 'network.json').exists():
        score += 4
    return score


def _copy_best_raw_source(source: Path, target: Path) -> None:
    if source == target:
        return
    target.mkdir(parents=True, exist_ok=True)
    for filename in ('result.html', 'result.txt', 'network.json', 'result.png'):
        src = source / filename
        dst = target / filename
        if not src.exists():
            continue
        try:
            if not dst.exists() or src.stat().st_size > dst.stat().st_size:
                shutil.copy2(src, dst)
        except Exception:
            pass


def _read_cached_folder_facts(profile: BirthProfile, folder: Path) -> ForcetellerFacts | None:
    """Read one saved source folder without performing any external request.

    A partial raw-source reparse is attempted at most once per parser revision in the normal
    cache-first mode.  This prevents the same large result.html from being reparsed on every
    page load just because optional enrichment such as 용신/대운 is absent.
    """
    facts_path = folder / 'forceteller_facts.json'
    cached = read_json(facts_path, {}) or {}
    if not cached:
        legacy_manifest = read_json(folder / 'forceteller_profile.json', {}) or {}
        if isinstance(legacy_manifest, dict) and isinstance(legacy_manifest.get('chart'), dict):
            normalized_profile = _legacy_profile_mapping(legacy_manifest)
            if normalized_profile:
                cached = dict(legacy_manifest)
                cached['profile'] = normalized_profile

    metadata = read_json(folder / 'metadata.json', {}) or {}
    partial_already_tried = (
        metadata.get('reparse_status') == 'partial'
        and metadata.get('reparse_parser_version') == SETTINGS.parser_version
        and not SETTINGS.retry_partial_facts
    )
    parser_changed = metadata.get('parser_version') != SETTINGS.parser_version
    needs_reparse = parser_changed or _cached_facts_need_reparse(
        cached if isinstance(cached, dict) else {}, folder
    )
    # If this exact parser already tried the raw source and only optional fields stayed empty,
    # reuse the source-backed cache instead of repeating local parsing on every request.
    if partial_already_tried and isinstance(cached, dict) and cached:
        try:
            if _cached_facts_usable(cached, False):
                needs_reparse = False
        except Exception:
            pass

    parsed: ForcetellerFacts | None = None
    if needs_reparse:
        parsed = _reparse_cached_source(profile, folder)
    elif isinstance(cached, dict) and cached:
        try:
            parsed = _facts_from_dict(cached)
        except Exception:
            parsed = None
    if parsed is not None:
        parsed.profile = profile
    return parsed


def _resolve_best_cached_facts(
    profile: BirthProfile,
    *,
    force: bool = False,
    require_fortune: bool = False,
) -> tuple[ForcetellerFacts | None, Path]:
    """Resolve a reusable source cache before considering any browser collection.

    The canonical current cache is a fast path.  Historical project/output scanning is only
    performed when that direct cache is absent or unusable, which keeps repeated analyses fast
    even when many old candidate folders exist on disk.
    """
    canonical_folder = SETTINGS.forceteller_dir / profile_key(profile.as_dict())
    if force:
        return None, canonical_folder

    # Fast path: most repeat requests should stop here without walking legacy directories.
    if canonical_folder.exists() and canonical_folder.is_dir():
        direct = _read_cached_folder_facts(profile, canonical_folder)
        if direct is not None:
            direct_data = direct.as_dict()
            direct_usable = _cached_facts_usable(direct_data, False)
            if direct_usable:
                return direct, canonical_folder

    rows: list[tuple[int, ForcetellerFacts, Path]] = []
    for folder in _matching_profile_cache_folders(profile):
        parsed = _read_cached_folder_facts(profile, folder)
        if parsed is None:
            continue
        rows.append((_facts_completeness_score(parsed, folder), parsed, folder))

    if not rows:
        return None, canonical_folder

    rows.sort(key=lambda row: row[0], reverse=True)
    _, merged, best_folder = rows[0]
    for _, other, _folder in rows[1:]:
        merged = _merge_missing_verified_fields(merged, other)
    merged.profile = profile

    merged_data = merged.as_dict()
    usable = _cached_facts_usable(merged_data, False)

    canonical_folder.mkdir(parents=True, exist_ok=True)
    if usable:
        _copy_best_raw_source(best_folder, canonical_folder)
        write_json(canonical_folder / 'forceteller_facts.json', merged_data)
        meta = read_json(canonical_folder / 'metadata.json', {}) or {}
        meta.update({
            'profile': profile.as_dict(),
            'parser_version': SETTINGS.parser_version,
            'merged_from_cache': True,
            'cache_reusable': True,
            'cache_complete': bool(str(merged.strength_label or '').strip() and merged.useful_elements),
        })
        write_json(canonical_folder / 'metadata.json', meta)
    else:
        write_json(canonical_folder / 'forceteller_facts.merge_partial.json', merged_data)
    return (merged if usable else None), canonical_folder


def _profile_cache_folder(profile: BirthProfile) -> tuple[Path, bool]:
    """Compatibility helper: always return the canonical output folder."""
    folder = SETTINGS.forceteller_dir / profile_key(profile.as_dict())
    return folder, folder.exists()

def _cached_facts_need_reparse(data: dict[str, Any], folder: Path) -> bool:
    """원문에는 정보가 있는데 예전 파서 결과에서 빠진 핵심 필드는 즉시 재파싱한다."""
    if not isinstance(data, dict):
        return True
    chart = data.get('chart') or {}
    if not chart.get('day_pillar'):
        return True
    html_path = folder / 'result.html'
    text_path = folder / 'result.txt'
    if not html_path.exists() and not text_path.exists():
        return False
    try:
        raw = ''
        if html_path.exists():
            raw += html_path.read_text(encoding='utf-8', errors='ignore')
        if text_path.exists():
            raw += '\n' + text_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return False
    # 원문에서 명확하게 제공하는 항목인데 cache facts에 없으면 stale cache로 본다.
    if ('data-test-id="singang"' in raw or '신강/신약지수' in raw) and not str(_legacy_value(data, 'strength_label', '') or '').strip():
        return True
    if re.search(r'data-test-id=["\']daeun\d+top["\']', raw, re.I) and not (_legacy_value(data, 'daewoon', []) or []):
        return True
    if '용신' in raw and not (_legacy_value(data, 'useful_elements', []) or []):
        return True
    if '신살과 길성' in raw and not (_legacy_value(data, 'special_stars', []) or []):
        return True
    if '신살과 길성' in raw and (_legacy_value(data, 'special_stars', []) or []) and not (_legacy_value(data, 'special_star_positions', {}) or {}):
        return True
    return False


def _clone_facts_for_profile(facts: ForcetellerFacts, profile: BirthProfile) -> ForcetellerFacts:
    """Return an independent facts object while preserving the caller's display identity."""
    cloned = deepcopy(facts)
    cloned.profile = profile
    return cloned


def collect_many_facts(
    profiles: list[BirthProfile],
    force: bool = False,
    require_fortune_for_first: bool = False,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[ForcetellerFacts]:
    """Collect only genuinely missing unique birth identities.

    Cache lookup always happens before Playwright starts.  If the same birth identity appears
    more than once in a group/request, it is resolved or collected once and cloned back to the
    original positions so names/order never change.
    """
    if not profiles:
        return []

    results: list[ForcetellerFacts | None] = [None] * len(profiles)

    identity_rows: dict[str, list[tuple[int, BirthProfile]]] = {}
    unique_profiles: list[tuple[str, BirthProfile]] = []
    for i, profile in enumerate(profiles):
        identity = stable_hash(canonical_profile_identity(profile.as_dict()))
        if identity not in identity_rows:
            identity_rows[identity] = []
            unique_profiles.append((identity, profile))
        identity_rows[identity].append((i, profile))

    source_total = max(1, len(unique_profiles))
    completed_sources = 0
    pending: list[tuple[str, BirthProfile, Path]] = []

    def assign(identity: str, facts: ForcetellerFacts) -> None:
        for index, requested_profile in identity_rows[identity]:
            results[index] = _clone_facts_for_profile(facts, requested_profile)

    def emit(message: str) -> None:
        if progress_callback:
            progress_callback(min(1.0, completed_sources / source_total), message)

    def progress_message(profile: BirthProfile | None = None, *, active: bool = False) -> str:
        if profiles and all((p.name or '') == '추천 후보' for p in profiles):
            subject = '추천 후보 자료'
        elif len(profiles) > 2:
            subject = '구성원 원국 자료'
        else:
            subject = f'{(profile.name if profile else "원국") or "원국"} 자료'
        if active:
            next_index = min(source_total, completed_sources + 1)
            return f'저장된 자료에 없는 {subject} {next_index}/{source_total}번째만 새로 확인하고 있어요.'
        return f'{subject} {completed_sources}/{source_total}개 준비됐어요.'

    for unique_index, (identity, profile) in enumerate(unique_profiles):
        # require_fortune_for_first refers to the original first profile.
        first_original_index = identity_rows[identity][0][0]
        require_fortune = bool(require_fortune_for_first and first_original_index == 0)
        resolved, folder = _resolve_best_cached_facts(
            profile, force=force, require_fortune=require_fortune
        )
        if resolved is not None:
            assign(identity, resolved)
            completed_sources += 1
            continue
        folder.mkdir(parents=True, exist_ok=True)
        pending.append((identity, profile, folder))

    cache_hits = completed_sources
    duplicate_saved = len(profiles) - len(unique_profiles)
    if progress_callback and cache_hits:
        duplicate_note = f' · 중복 원국 {duplicate_saved}건은 1회만 사용' if duplicate_saved else ''
        if pending:
            progress_callback(
                min(1.0, cache_hits / source_total),
                f'저장된 원국 자료 {cache_hits}/{source_total}개를 바로 사용했어요. 새 조회는 {len(pending)}개만 진행합니다{duplicate_note}.',
            )
        else:
            progress_callback(
                1.0,
                f'저장된 원국 자료 {cache_hits}/{source_total}개를 사용했어요. 외부 재조회는 하지 않았어요{duplicate_note}.',
            )

    if not pending:
        if progress_callback:
            progress_callback(1.0, '저장된 원국 자료를 모두 불러왔어요.')
        if any(x is None for x in results):
            raise RuntimeError('캐시 원국 결과 일부가 비어 있습니다.')
        return [x for x in results if x is not None]

    emit(progress_message(pending[0][1], active=True))

    if sync_playwright is None:
        for identity, profile, folder in pending:
            fallback = _fallback_preserving_existing(profile, folder, _friendly_collection_warning())
            write_json(folder / 'forceteller_facts.json', fallback.as_dict())
            assign(identity, fallback)
            completed_sources += 1
            emit(progress_message(profile))
        if progress_callback:
            progress_callback(1.0, '필요한 원국 자료를 모두 확인했어요.')
        return [x for x in results if x is not None]

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(SETTINGS.browser_profile_dir),
                headless=SETTINGS.headless,
                viewport={'width': 1440, 'height': 1000},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                for identity, profile, folder in pending:
                    try:
                        emit(progress_message(profile, active=True))
                        if page.is_closed():
                            page = context.new_page()
                        collected = _collect_on_page(page, profile, folder)
                        assign(identity, collected)
                        completed_sources += 1
                        emit(progress_message(profile))
                    except Exception as exc:
                        _write_internal_error(folder, exc)
                        fallback = _fallback_preserving_existing(profile, folder, _friendly_collection_warning())
                        write_json(folder / 'forceteller_facts.json', fallback.as_dict())
                        assign(identity, fallback)
                        completed_sources += 1
                        emit(progress_message(profile))
                        try:
                            if page.is_closed():
                                page = context.new_page()
                            else:
                                page.goto('about:blank', wait_until='load', timeout=5000)
                        except Exception:
                            pass
            finally:
                try:
                    context.close()
                except Exception:
                    pass
    except Exception as exc:
        for identity, profile, folder in pending:
            # A pending identity may already have been filled before the context itself failed.
            indices = [idx for idx, _ in identity_rows[identity]]
            if any(results[idx] is None for idx in indices):
                _write_internal_error(folder, exc)
                fallback = _fallback_preserving_existing(profile, folder, _friendly_collection_warning('browser'))
                write_json(folder / 'forceteller_facts.json', fallback.as_dict())
                assign(identity, fallback)
                completed_sources += 1
                emit(progress_message(profile))

    if progress_callback:
        progress_callback(1.0, '필요한 원국 자료를 모두 확인했어요.')
    if any(x is None for x in results):
        raise RuntimeError('원국 수집 결과 일부가 비어 있어 분석을 계속할 수 없습니다.')
    return [x for x in results if x is not None]


def collect_facts(
    profile: BirthProfile,
    force: bool = False,
    require_fortune: bool = False,
    progress_callback: Callable[[float, str], None] | None = None,
) -> ForcetellerFacts:
    return collect_many_facts(
        [profile], force=force, require_fortune_for_first=require_fortune, progress_callback=progress_callback
    )[0]
