from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Any, Callable

from explain import build_pair_report
from models import ForcetellerFacts, Mode
from scoring import score_pair


GROUP_CONTEXTS: dict[str, dict[str, str]] = {
    'friends': {
        'label': '친구·지인 모임',
        'summary': '친구나 지인 사이의 편안함, 대화 흐름, 함께 움직이는 리듬과 갈등 조율을 중심으로 봅니다.',
        'role_suffix': '친구·지인 모임 안에서',
    },
    'work': {
        'label': '직장·프로젝트 팀',
        'summary': '협업 방식, 역할 분담, 의사결정, 실행 속도와 의견 충돌을 조율하는 구조를 중심으로 봅니다.',
        'role_suffix': '업무·프로젝트 관계 안에서',
    },
    'family': {
        'label': '가족',
        'summary': '가까운 생활 관계에서 반복되는 정서적 거리, 돌봄, 책임, 생활 리듬과 갈등 회복 방식을 중심으로 봅니다.',
        'role_suffix': '가족이라는 가까운 생활 관계 안에서',
    },
    'hobby': {
        'label': '동호회·취미 모임',
        'summary': '같이 활동할 때의 호흡, 대화, 추진력, 참여 방식과 모임을 오래 유지하는 리듬을 중심으로 봅니다.',
        'role_suffix': '취미·활동 모임 안에서',
    },
    'mixed': {
        'label': '혼합 관계·기타',
        'summary': '한 가지 관계 유형으로 묶기 어려운 구성원들의 일반적인 비연인 관계 구조를 중심으로 봅니다.',
        'role_suffix': '이 그룹 안에서',
    },
}


def _context_info(context: str) -> dict[str, str]:
    return GROUP_CONTEXTS.get(context, GROUP_CONTEXTS['friends'])


def _connected_components(names: list[str], matrix: list[list[float]], threshold: float = 75.0) -> list[list[str]]:
    n = len(names)
    seen: set[int] = set()
    groups: list[list[str]] = []
    for start in range(n):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp: list[str] = []
        while stack:
            i = stack.pop()
            comp.append(names[i])
            for j in range(n):
                if j in seen or i == j:
                    continue
                if matrix[i][j] >= threshold:
                    seen.add(j)
                    stack.append(j)
        groups.append(comp)
    return sorted(groups, key=len, reverse=True)


def _role_map(member: ForcetellerFacts, context: str) -> dict[str, float]:
    tg = member.ten_gods
    if context == 'work':
        return {
            '아이디어·제안형': tg.get('식신', 0) + tg.get('상관', 0),
            '기준·운영형': tg.get('정관', 0) + tg.get('편관', 0),
            '지원·학습형': tg.get('정인', 0) + tg.get('편인', 0),
            '실행·성과형': tg.get('정재', 0) + tg.get('편재', 0),
            '협업·주도형': tg.get('비견', 0) + tg.get('겁재', 0),
        }
    if context == 'family':
        return {
            '대화·분위기 환기형': tg.get('식신', 0) + tg.get('상관', 0),
            '기준·책임형': tg.get('정관', 0) + tg.get('편관', 0),
            '돌봄·지원형': tg.get('정인', 0) + tg.get('편인', 0),
            '생활 실무형': tg.get('정재', 0) + tg.get('편재', 0),
            '유대·주도형': tg.get('비견', 0) + tg.get('겁재', 0),
        }
    if context == 'hobby':
        return {
            '대화·아이디어형': tg.get('식신', 0) + tg.get('상관', 0),
            '약속·기준형': tg.get('정관', 0) + tg.get('편관', 0),
            '상담·지원형': tg.get('정인', 0) + tg.get('편인', 0),
            '활동·실행형': tg.get('정재', 0) + tg.get('편재', 0),
            '친밀·주도형': tg.get('비견', 0) + tg.get('겁재', 0),
        }
    return {
        '대화·아이디어형': tg.get('식신', 0) + tg.get('상관', 0),
        '기준·정리형': tg.get('정관', 0) + tg.get('편관', 0),
        '상담·지원형': tg.get('정인', 0) + tg.get('편인', 0),
        '현실 실행형': tg.get('정재', 0) + tg.get('편재', 0),
        '동료·주도형': tg.get('비견', 0) + tg.get('겁재', 0),
    }



def _role_guide(role: str, context: str) -> str:
    guides = {
        'work': {
            '아이디어·제안형': '새 아이디어나 문제 개선안을 먼저 꺼내고 초안을 만드는 역할',
            '기준·운영형': '기준·품질·일정과 책임선을 정리해 팀이 흔들리지 않게 하는 역할',
            '지원·학습형': '자료를 모으고 검토해 다른 사람이 판단하기 쉽게 근거를 보강하는 역할',
            '실행·성과형': '해야 할 일을 실제 일정과 결과물로 연결하고 마감을 챙기는 역할',
            '협업·주도형': '여러 사람 사이에서 일을 나누고 먼저 움직여 흐름을 만드는 역할',
            '조율·지원형': '한쪽 역할로 단정하기보다 필요한 정보를 연결하고 빈틈을 메우는 역할',
        },
        'family': {
            '대화·분위기 환기형': '답답한 분위기를 풀고 말문을 열어 주는 역할',
            '기준·책임형': '가족의 약속과 책임 범위를 분명히 정리하는 역할',
            '돌봄·지원형': '상대의 상태를 살피고 필요한 정보나 도움을 연결하는 역할',
            '생활 실무형': '집안일·일정·비용처럼 실제 생활을 챙기는 역할',
            '유대·주도형': '가족 구성원을 모으고 함께 움직일 일을 먼저 시작하는 역할',
            '관계 조율형': '특정 역할로 몰기보다 필요한 때 대화와 생활 정보를 연결하는 역할',
        },
        'hobby': {
            '대화·아이디어형': '새 활동이나 재미있는 아이디어를 제안하는 역할',
            '약속·기준형': '일정·회비·운영 규칙을 정리하는 역할',
            '상담·지원형': '새 구성원이 적응하도록 설명하고 필요한 정보를 챙기는 역할',
            '활동·실행형': '준비물과 실제 진행을 맡아 활동을 굴리는 역할',
            '친밀·주도형': '사람들을 모으고 참여 흐름을 만드는 역할',
            '참여 조율형': '특정 역할보다 상황에 따라 준비·안내·참여를 유연하게 돕는 역할',
        },
        'friends': {
            '대화·아이디어형': '대화를 열고 모임이나 약속 아이디어를 꺼내는 역할',
            '기준·정리형': '약속 시간·장소·기준을 깔끔하게 정리하는 역할',
            '상담·지원형': '상대 이야기를 듣고 필요한 도움이나 정보를 연결하는 역할',
            '현실 실행형': '계획을 실제 약속과 행동으로 옮기는 역할',
            '동료·주도형': '사람들을 모으고 먼저 움직여 모임 흐름을 만드는 역할',
            '관계 조율형': '특정 역할로 단정하기보다 필요할 때 대화와 약속을 연결하는 역할',
        },
    }
    selected = guides.get(context, guides.get('friends', {}))
    return selected.get(role, f'{role} 쪽의 역할')


def _group_guide(context: str) -> str:
    if context == 'work':
        return ('그룹 결과는 함께 일하고 소통하는 방식으로 해석합니다. '
                '누가 누구와 편하게 협업하는지, 어디에서 역할이나 결정 방식이 엇갈리는지, 누가 연결자 역할을 하기 쉬운지를 중심으로 봅니다. '
                '실제 업무 성과는 경력·직무권한·조직문화가 더 직접적인 변수이므로 이 결과는 역할과 소통 규칙을 정하는 참고자료로 사용하세요.')
    if context == 'family':
        return ('가족 결과는 가까운 생활 안에서의 대화·책임·돌봄·개인 경계를 중심으로 봅니다. '
                '실제 관계는 오랜 경험과 가족 역할의 영향을 크게 받으므로, 결과는 반복되는 생활 갈등을 더 구체적인 규칙으로 바꾸는 참고자료로 사용하세요.')
    if context == 'hobby':
        return ('모임 결과는 함께 활동할 때의 참여 리듬·약속·운영 역할·대화를 중심으로 봅니다. '
                '실제 친밀도나 실력과는 별개이므로 모임의 재미와 운영 부담을 조절하는 참고자료로 사용하세요.')
    if context == 'mixed':
        return ('혼합 그룹은 관계를 친구·직장·가족 중 하나로 단정하지 않고, 누가 누구와 편하게 소통하는지와 '
                '어디에서 역할·기대·경계를 먼저 확인해야 하는지를 중심으로 봅니다. 실제 관계의 목적이 서로 다를 수 있으므로 '
                '공통 규칙을 정하기보다 각 관계의 기대를 먼저 확인하는 참고자료로 사용하세요.')
    return ('그룹 결과는 누가 누구와 편하게 소통하는지, 어디에서 연락·약속·경계가 엇갈리는지, '
            '누가 여러 사람을 잇기 쉬운지를 중심으로 봅니다. 실제 관계의 역사와 신뢰가 더 직접적인 변수이므로 참고자료로 활용하세요.')


def _team_actions(context: str, strongest: dict[str, Any], weakest: dict[str, Any], bridge_name: str) -> list[str]:
    if context == 'work':
        return [
            f'{strongest["a"]}님과 {strongest["b"]}님은 함께 초안이나 초기 협업을 맡겨 자연스러운 연결을 활용해 보세요.',
            f'{weakest["a"]}님과 {weakest["b"]}님이 함께 일할 때는 요청 목적·마감·최종 결정자를 먼저 정하는 편이 좋습니다.',
            f'{bridge_name}님에게 모든 갈등을 떠넘기기보다, 정보가 끊기는 지점을 연결하는 조율 역할을 제한적으로 맡기는 편이 좋습니다.',
            '회의에서는 제안자·검토자·최종 결정자를 구분하고, 결정 후에는 담당자와 마감 시점을 한 줄로 남기는 방식을 권합니다.',
        ]
    if context == 'family':
        return [
            f'{strongest["a"]}님과 {strongest["b"]}님은 서로 부담 없이 도움을 주고받기 쉬운 연결로 활용할 수 있습니다.',
            f'{weakest["a"]}님과 {weakest["b"]}님은 집안일·연락·개인시간·비용처럼 반복되는 생활 기준을 말로 확인하는 편이 좋습니다.',
            f'{bridge_name}님에게 중재를 모두 맡기지 말고 필요한 정보만 전달하는 연결 역할로 제한해 주세요.',
            '가까운 사이라도 부탁·돌봄·비용을 당연하게 기대하지 말고 누가 무엇을 맡는지 구체적으로 정하는 편이 좋습니다.',
        ]
    if context == 'hobby':
        return [
            f'{strongest["a"]}님과 {strongest["b"]}님은 새 활동 준비나 첫 진행을 함께 맡겨 볼 수 있습니다.',
            f'{weakest["a"]}님과 {weakest["b"]}님은 참여 강도·일정·회비·준비 역할을 미리 맞추는 편이 좋습니다.',
            f'{bridge_name}님은 새 구성원이나 서로 다른 소그룹 사이의 정보 공유를 돕는 역할에 잘 활용할 수 있습니다.',
            '운영 역할을 몇 사람에게 고정하지 말고 순환해 취미가 의무처럼 느껴지지 않게 하는 편이 좋습니다.',
        ]
    if context == 'mixed':
        return [
            f'{strongest["a"]}님과 {strongest["b"]}님은 함께 처리할 일이 생겼을 때 비교적 자연스럽게 연결되는 조합입니다.',
            f'{weakest["a"]}님과 {weakest["b"]}님은 서로의 관계 목적과 기대 수준을 먼저 확인한 뒤 역할이나 연락 방식을 정하는 편이 좋습니다.',
            f'{bridge_name}님은 여러 관계 사이에서 정보가 끊길 때 전달을 돕기 쉬운 위치이지만 중재 책임을 고정해서 맡길 필요는 없습니다.',
            '관계 유형이 섞여 있을수록 모두에게 같은 친밀도·연락 빈도·책임을 기대하지 말고 필요한 범위를 관계별로 확인하는 편이 좋습니다.',
        ]
    return [
        f'{strongest["a"]}님과 {strongest["b"]}님은 약속이나 활동을 함께 시작할 때 비교적 자연스럽게 호흡을 맞추기 쉬운 편입니다.',
        f'{weakest["a"]}님과 {weakest["b"]}님은 연락 빈도·약속 변경·개인시간에 대한 기준을 직접 말하는 편이 좋습니다.',
        f'{bridge_name}님에게 모든 중재를 맡기기보다 사람 사이 정보가 끊길 때만 연결 역할을 부탁하는 편이 좋습니다.',
        '친한 관계일수록 상대도 당연히 알 거라고 가정하지 말고, 원하는 것과 부담스러운 것을 짧고 구체적으로 말하는 편이 좋습니다.',
    ]

def _group_summary(
    context: str,
    context_label: str,
    strongest: dict[str, Any],
    weakest: dict[str, Any],
    bridge_name: str,
) -> str:
    base = (
        f'이 {context_label}에서는 {strongest["a"]}–{strongest["b"]} 연결이 가장 자연스럽고, '
        f'{weakest["a"]}–{weakest["b"]}는 서로의 기준을 더 구체적으로 확인할 필요가 있습니다. '
    )
    tails = {
        'work': f'{bridge_name}님은 정보가 끊기는 지점을 이어 주는 조율 창구로 활용하면 협업 흐름을 안정시키는 데 도움이 될 수 있습니다.',
        'family': f'{bridge_name}님은 가족 사이 정보가 엇갈릴 때 연결을 돕기 쉬운 위치지만, 모든 갈등의 중재 책임을 맡길 필요는 없습니다.',
        'hobby': f'{bridge_name}님은 서로 다른 참여자 사이의 정보 공유와 새 구성원 적응을 돕기 쉬운 위치입니다.',
        'mixed': f'{bridge_name}님은 관계 목적이 다른 구성원 사이에서 필요한 정보를 연결하기 쉬운 위치입니다.',
        'friends': f'{bridge_name}님은 여러 사람 사이의 연락과 약속을 자연스럽게 이어 주기 쉬운 위치입니다.',
    }
    return base + tails.get(context, tails['friends'])


def analyze_group(
    members: list[ForcetellerFacts],
    mode: Mode = 'friend',
    *,
    context: str = 'friends',
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    if len(members) < 2:
        raise ValueError('그룹 분석은 최소 2명이 필요합니다.')

    # 그룹 분석은 연인용 배우자궁·배우자성 축을 쓰지 않는다.
    # 과거 mode='love' 요청이 들어와도 비연인 그룹 기준으로 통일한다.
    scoring_mode: Mode = 'friend'
    context = context if context in GROUP_CONTEXTS else 'friends'
    context_info = _context_info(context)

    names = [m.profile.name or f'멤버{i+1}' for i, m in enumerate(members)]
    n = len(members)
    matrix = [[100.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    pairs: list[dict[str, Any]] = []
    all_scores: list[float] = []
    averages = [0.0] * n
    total_pairs = max(1, n * (n - 1) // 2)
    completed_pairs = 0

    for i in range(n):
        for j in range(i + 1, n):
            result = score_pair(members[i], members[j], scoring_mode)
            matrix[i][j] = matrix[j][i] = result.total
            all_scores.append(result.total)
            pair_report = build_pair_report(members[i], members[j], result, context=context)
            pair_report['context'] = context
            pairs.append({
                'a_index': i,
                'b_index': j,
                'a': names[i],
                'b': names[j],
                'score': result.total,
                'label': pair_report.get('label', result.label),
                'report': pair_report,
            })
            completed_pairs += 1
            if progress_callback:
                progress_callback(
                    completed_pairs / total_pairs,
                    f'{names[i]} · {names[j]} 연결을 계산했어요. ({completed_pairs}/{total_pairs})',
                )

    for i in range(n):
        vals = [matrix[i][j] for j in range(n) if j != i]
        averages[i] = round(mean(vals), 1)

    avg = mean(all_scores)
    med = median(all_scores)
    minimum = min(all_scores)
    group_score = round(avg * 0.70 + med * 0.15 + minimum * 0.15, 1)
    strongest = max(pairs, key=lambda x: x['score'])
    weakest = min(pairs, key=lambda x: x['score'])

    anchor_idx = max(range(n), key=lambda i: averages[i])
    bridge_idx = max(
        range(n),
        key=lambda i: averages[i]
        - (pstdev([matrix[i][j] for j in range(n) if j != i]) if n > 2 else 0) * 0.35,
    )

    role_rows = []
    fallback_roles = {
        'work': '조율·지원형',
        'family': '관계 조율형',
        'hobby': '참여 조율형',
        'friends': '관계 조율형',
        'mixed': '관계 조율형',
    }
    for i, member in enumerate(members):
        role_candidates = _role_map(member, context)
        max_value = max(role_candidates.values(), default=0.0)
        role = max(role_candidates, key=role_candidates.get) if max_value > 0 else fallback_roles.get(context, '관계 조율형')
        guide = _role_guide(role, context)
        relative_notes: list[str] = []
        if i == anchor_idx:
            relative_notes.append('여러 구성원과의 평균 연결이 비교적 고르게 높은 편이라 공통 기준을 잡는 데 활용하기 쉽습니다')
        if i == bridge_idx:
            relative_notes.append('관계 편차가 상대적으로 작아 서로 다른 사람 사이의 정보 연결을 돕기 쉬운 위치입니다')
        topology_note = (' ' + ' '.join(relative_notes)) if relative_notes else ''
        role_rows.append({
            'index': i,
            'name': names[i],
            'average_connection': averages[i],
            'role': role,
            'role_reason': (
                f'{names[i]}님의 원국 성향을 기준으로는 {guide}이 자연스러운 편입니다.'
                f'{topology_note} 실제 직무·가족 역할을 정하는 판정이 아니라, 이 그룹에서 역할을 나눌 때 참고할 제안입니다.'
            ),
            'role_guide': guide,
            'is_anchor': i == anchor_idx,
            'is_bridge': i == bridge_idx,
        })

    clusters = _connected_components(names, matrix, 75.0)
    unknown_time_names = [m.profile.name for m in members if not m.profile.time_known]
    return {
        'mode': scoring_mode,
        'context': context,
        'context_label': context_info['label'],
        'context_note': context_info['summary'],
        'group_score': group_score,
        'group_label': _group_label(group_score),
        'names': names,
        'matrix': matrix,
        'pairwise': pairs,
        'strongest_pair': strongest,
        'weakest_pair': weakest,
        'anchor': {'name': names[anchor_idx], 'average': averages[anchor_idx]},
        'bridge': {'name': names[bridge_idx], 'average': averages[bridge_idx]},
        'roles': role_rows,
        'clusters': clusters,
        'summary': _group_summary(
            context,
            context_info['label'],
            strongest,
            weakest,
            names[bridge_idx],
        ),
        'team_actions': _team_actions(context, strongest, weakest, names[bridge_idx]),
        'guide': _group_guide(context),
        'time_accuracy': {
            'all_known': not unknown_time_names,
            'unknown_names': unknown_time_names,
            'label': '전원 시주 포함' if not unknown_time_names else '출생시간 미상 구성원 포함',
            'description': (
                '모든 구성원의 출생시간이 확인되어 시주까지 포함했습니다.'
                if not unknown_time_names
                else f'{", ".join(unknown_time_names)}의 출생시간이 없어 해당 구성원은 시주를 제외했습니다. '
                     '관계 행렬은 확정 가능한 연주·월주·일주를 중심으로 계산하며 시간에 따라 달라질 수 있는 세부 관계는 미확정입니다.'
            ),
        },
    }


def _group_label(score: float) -> str:
    if score >= 85:
        return '전체적으로 매우 조화로운 그룹'
    if score >= 75:
        return '강점 연결이 좋은 그룹'
    if score >= 65:
        return '대체로 잘 섞이지만 일부 조율이 필요한 그룹'
    if score >= 55:
        return '장단점이 함께 나타나는 그룹'
    if score >= 45:
        return '관계 규칙과 역할 정리가 중요한 그룹'
    return '마찰 관리와 역할 분리가 특히 중요한 그룹'
