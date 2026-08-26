from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DUMMY_PATTERNS = [
    r'수정이\s*필요', r'대체로\s*좋', r'유지합니다', r'placeholder', r'dummy',
    r'<source_data>', r'json\s*schema', r'프롬프트', r'작성\s*과정', r'검토\s*결과',
    r'모델이\s*(?:생성|판단)', r'ai가\s*(?:생성|판단)',
]
BROKEN_PATTERNS = [r'습니다보다', r'입니다입니다', r'합니다합니다', r'\.\s*\.\s*\.\s*\.']
# 사용자에게 실질적인 의미를 주지 않고 "원국/근거를 보라"고만 떠넘기는 문장.
EMPTY_GUIDANCE_PATTERNS = [
    r'^\s*(?:원국|원국\s*조합|명리\s*구조|명리\s*근거).{0,20}(?:보세요|확인하세요|참고하세요)\.?\s*$',
    r'^\s*(?:상세|세부)\s*(?:구조|명리)\s*해설.{0,12}(?:보세요|참고하세요)\.?\s*$',
]


@dataclass
class QualityIssue:
    path: str
    reason: str
    value: str


def clean_text(value: str) -> str:
    text = ' '.join(str(value or '').split())
    text = re.sub(r'\s+([,.!?])', r'\1', text)
    return text.strip()


def lint_text(value: str, path: str = '') -> list[QualityIssue]:
    text = str(value or '')
    issues: list[QualityIssue] = []
    for pattern in DUMMY_PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append(QualityIssue(path, f'메타/더미 문장 패턴: {pattern}', text[:200]))
    for pattern in BROKEN_PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append(QualityIssue(path, f'문법 파손 패턴: {pattern}', text[:200]))
    for pattern in EMPTY_GUIDANCE_PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append(QualityIssue(path, '사용자에게 의미 없는 근거 확인 지시문', text[:200]))
    if text.count('(') != text.count(')'):
        issues.append(QualityIssue(path, '괄호 개수가 맞지 않음', text[:200]))
    return issues


def lint_object(node: Any, path: str = 'root') -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if isinstance(node, str):
        return lint_text(node, path)
    if isinstance(node, list):
        for i, value in enumerate(node):
            issues.extend(lint_object(value, f'{path}[{i}]'))
    elif isinstance(node, dict):
        for key, value in node.items():
            issues.extend(lint_object(value, f'{path}.{key}'))
    return issues


def replace_bad_text(
    node: Any,
    fallback: str = (
        '현재 확인된 정보만으로는 이 항목을 단정하기 어렵습니다. '
        '실제 생활에서는 반복되는 행동, 대화 방식, 일정·돈·역할 분담을 함께 확인해 주세요.'
    ),
) -> Any:
    if isinstance(node, str):
        return fallback if lint_text(node) else clean_text(node)
    if isinstance(node, list):
        return [replace_bad_text(x, fallback) for x in node]
    if isinstance(node, dict):
        return {k: replace_bad_text(v, fallback) for k, v in node.items()}
    return node


def _text_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_text(data: dict[str, Any], key: str, path: str, issues: list[QualityIssue]) -> None:
    value = data.get(key)
    if not _text_present(value):
        issues.append(QualityIssue(f'{path}.{key}', '필수 사용자 해설이 비어 있음', str(value)[:200]))
    elif lint_text(value, f'{path}.{key}'):
        issues.extend(lint_text(value, f'{path}.{key}'))


def _require_list(data: dict[str, Any], key: str, path: str, issues: list[QualityIssue]) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        issues.append(QualityIssue(f'{path}.{key}', '필수 구조화 목록이 비어 있음', str(value)[:200]))
        return []
    return value


def validate_profile_report(report: Any, *, path: str = 'profile_report') -> list[QualityIssue]:
    """화면이 실제로 쓰는 프로필 구조가 빠짐없이 채워졌는지 검사한다.

    신살처럼 원국에 따라 비어 있을 수 있는 값은 필수로 강제하지 않는다. 대신 사용자에게
    반드시 보여 주는 성향/직장/재물/관계/연애/학습과 원국 4기둥 구조를 확인한다.
    """
    issues: list[QualityIssue] = []
    if not isinstance(report, dict):
        return [QualityIssue(path, '프로필 해설이 dict가 아님', repr(report)[:200])]

    for key in ('overview', 'personality', 'career', 'wealth', 'relationships', 'romance', 'study'):
        _require_text(report, key, path, issues)

    for key in (
        'personality_dimensions', 'career_dimensions', 'wealth_dimensions',
        'relationship_dimensions', 'romance_dimensions', 'study_dimensions',
    ):
        rows = _require_list(report, key, path, issues)
        for i, row in enumerate(rows):
            row_path = f'{path}.{key}[{i}]'
            if not isinstance(row, dict):
                issues.append(QualityIssue(row_path, '구조화 해설 행이 dict가 아님', repr(row)[:200]))
                continue
            for field in ('title', 'assessment', 'practical'):
                _require_text(row, field, row_path, issues)

    chart = report.get('chart')
    if not isinstance(chart, dict):
        issues.append(QualityIssue(f'{path}.chart', '원국 표시 구조가 없음', repr(chart)[:200]))
    else:
        pillars = chart.get('pillars')
        expected = ['hour', 'day', 'month', 'year']
        if not isinstance(pillars, list) or [row.get('key') for row in pillars if isinstance(row, dict)] != expected:
            issues.append(QualityIssue(f'{path}.chart.pillars', '시주→일주→월주→연주 구조가 맞지 않음', repr(pillars)[:200]))
        else:
            for i, row in enumerate(pillars):
                if not _text_present(row.get('value')):
                    issues.append(QualityIssue(f'{path}.chart.pillars[{i}].value', '기둥 값이 비어 있음', repr(row)[:200]))

    time_accuracy = report.get('time_accuracy')
    if not isinstance(time_accuracy, dict) or not _text_present(time_accuracy.get('label')):
        issues.append(QualityIssue(f'{path}.time_accuracy', '출생시간 정확도 표시가 없음', repr(time_accuracy)[:200]))
    return issues


def validate_fortunes(fortunes: Any, *, path: str = 'fortunes') -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if not isinstance(fortunes, dict):
        return [QualityIssue(path, '운세 구조가 dict가 아님', repr(fortunes)[:200])]
    for key in ('yearly', 'monthly', 'daily'):
        row = fortunes.get(key)
        row_path = f'{path}.{key}'
        if not isinstance(row, dict):
            issues.append(QualityIssue(row_path, '기간별 운세 구조가 없음', repr(row)[:200]))
            continue
        for field in ('label', 'focus', 'summary'):
            _require_text(row, field, row_path, issues)
        if not isinstance(row.get('domains'), dict) or not row.get('domains'):
            issues.append(QualityIssue(f'{row_path}.domains', '생활영역별 운세가 비어 있음', repr(row.get('domains'))[:200]))
    daewoon = fortunes.get('daewoon')
    if not isinstance(daewoon, dict):
        issues.append(QualityIssue(f'{path}.daewoon', '대운 구조가 없음', repr(daewoon)[:200]))
    else:
        # 대운 원문이 실제로 없는 경우 available=False는 허용하되 설명 문장은 있어야 한다.
        if not _text_present(daewoon.get('summary')):
            issues.append(QualityIssue(f'{path}.daewoon.summary', '대운 설명이 비어 있음', repr(daewoon)[:200]))
    return issues


def validate_pair_report(report: Any, *, expected_a: str = '', expected_b: str = '', path: str = 'pair_report') -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if not isinstance(report, dict):
        return [QualityIssue(path, '1:1 해설이 dict가 아님', repr(report)[:200])]
    for key in ('title', 'label', 'overview'):
        _require_text(report, key, path, issues)
    score = report.get('score')
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
        issues.append(QualityIssue(f'{path}.score', '궁합 점수가 0~100 범위 숫자가 아님', repr(score)))
    for person_key, expected_name in (('person_a', expected_a), ('person_b', expected_b)):
        person = report.get(person_key)
        issues.extend(validate_profile_report(person, path=f'{path}.{person_key}'))
        if expected_name and isinstance(person, dict):
            title = str(report.get('title') or '')
            if expected_name not in title:
                issues.append(QualityIssue(f'{path}.title', f'{person_key} 이름이 제목과 매칭되지 않음', title[:200]))
    analysis = report.get('analysis')
    if not isinstance(analysis, dict):
        issues.append(QualityIssue(f'{path}.analysis', '관계 해설 구조가 없음', repr(analysis)[:200]))
    else:
        for key in ('each_needs', 'fit', 'friction_scene', 'communication', 'role_split', 'daily_life', 'long_term'):
            _require_text(analysis, key, f'{path}.analysis', issues)
    reality = report.get('reality_checks')
    if not isinstance(reality, list) or len([x for x in reality if _text_present(x)]) < 3:
        issues.append(QualityIssue(f'{path}.reality_checks', '실생활 체크 항목이 충분하지 않음', repr(reality)[:200]))
    return issues


def validate_group_analysis(analysis: Any, *, member_names: list[str], path: str = 'group_analysis') -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if not isinstance(analysis, dict):
        return [QualityIssue(path, '그룹 분석이 dict가 아님', repr(analysis)[:200])]
    names = analysis.get('names')
    if names != member_names:
        issues.append(QualityIssue(f'{path}.names', '그룹 구성원 순서/이름이 입력과 매칭되지 않음', repr(names)[:200]))
    n = len(member_names)
    matrix = analysis.get('matrix')
    if not isinstance(matrix, list) or len(matrix) != n or any(not isinstance(row, list) or len(row) != n for row in matrix):
        issues.append(QualityIssue(f'{path}.matrix', f'{n}×{n} 관계 행렬이 아님', repr(matrix)[:200]))
    else:
        for i in range(n):
            if float(matrix[i][i]) != 100.0:
                issues.append(QualityIssue(f'{path}.matrix[{i}][{i}]', '자기 자신 점수는 100이어야 함', repr(matrix[i][i])))
            for j in range(i + 1, n):
                if float(matrix[i][j]) != float(matrix[j][i]):
                    issues.append(QualityIssue(f'{path}.matrix[{i}][{j}]', '관계 행렬이 대칭이 아님', f'{matrix[i][j]} != {matrix[j][i]}'))
    pairwise = analysis.get('pairwise')
    expected_pairs = n * (n - 1) // 2
    if not isinstance(pairwise, list) or len(pairwise) != expected_pairs:
        issues.append(QualityIssue(f'{path}.pairwise', f'관계 수가 {expected_pairs}개가 아님', repr(len(pairwise) if isinstance(pairwise, list) else pairwise)))
    else:
        seen: set[tuple[int, int]] = set()
        for i, row in enumerate(pairwise):
            row_path = f'{path}.pairwise[{i}]'
            if not isinstance(row, dict):
                issues.append(QualityIssue(row_path, '관계 행이 dict가 아님', repr(row)[:200]))
                continue
            ai, bi = row.get('a_index'), row.get('b_index')
            if not isinstance(ai, int) or not isinstance(bi, int) or not (0 <= ai < bi < n):
                issues.append(QualityIssue(row_path, '관계 인덱스가 입력 구성원과 매칭되지 않음', repr(row)[:200]))
                continue
            seen.add((ai, bi))
            if row.get('a') != member_names[ai] or row.get('b') != member_names[bi]:
                issues.append(QualityIssue(row_path, '관계 이름이 인덱스의 구성원 이름과 다름', repr(row)[:200]))
            issues.extend(validate_pair_report(row.get('report'), expected_a=member_names[ai], expected_b=member_names[bi], path=f'{row_path}.report'))
        if len(seen) != expected_pairs:
            issues.append(QualityIssue(f'{path}.pairwise', '중복/누락 관계가 있음', repr(sorted(seen))[:200]))
    for key in ('summary', 'group_label', 'context_label'):
        _require_text(analysis, key, path, issues)
    actions = analysis.get('team_actions')
    if not isinstance(actions, list) or not any(_text_present(x) for x in actions):
        issues.append(QualityIssue(f'{path}.team_actions', '그룹에서 바로 쓸 수 있는 행동 팁이 비어 있음', repr(actions)[:200]))
    return issues


def ensure_no_contract_issues(issues: list[QualityIssue], *, label: str) -> None:
    """구조화 오류를 조용히 화면까지 흘려보내지 않는다."""
    if not issues:
        return
    sample = '; '.join(f'{x.path}: {x.reason}' for x in issues[:8])
    raise ValueError(f'{label} 데이터 구조 검증 실패: {sample}')
