from __future__ import annotations

# 로컬 개발용 통합 테스트 데이터입니다.
# /test 화면에서만 사용하며 일반 서비스 화면(/)에는 전달하지 않습니다.
# 배포 서버에서 원격 사용자에게 /test를 노출하지 않도록 app.py에서 localhost 접근만 허용합니다.


def _person(
    name: str,
    year: int,
    month: int,
    day: int,
    gender: str,
    hour: int | None = None,
    minute: int = 0,
) -> dict[str, object]:
    time_known = hour is not None
    row: dict[str, object] = {
        'name': name,
        'gender': gender,
        'calendar_type': 'solar',
        'year': year,
        'month': month,
        'day': day,
        'time_known': time_known,
        'country_code': 'KR',
        'country': '대한민국',
        'city': '',
    }
    if time_known:
        row['hour'] = int(hour)
        row['minute'] = int(minute)
    return row


FULL_TEST_FIXTURE: dict[str, object] = {
    'label': '전체 통합 테스트',
    'description': '내 사주 + 잘 맞는 사람 + 1:1 연인 궁합 + 직장·프로젝트 팀 그룹 궁합을 한 번에 확인합니다.',
    'build_matches': True,
    'profile': {
        **_person('배경은', 1994, 12, 7, 'F', 5, 30),
        'partner_gender': 'M',
    },
    'pair': {
        'mode': 'love',
        'profile': _person('이희천', 1998, 10, 26, 'M', 7, 47),
    },
    'group': {
        'context': 'work',
        'members': [
            _person('채다현', 1992, 4, 19, 'F', 15, 0),
            _person('이홍주', 1997, 5, 14, 'F', 10, 0),
            _person('김효진', 1995, 11, 29, 'F', 6, 35),
            _person('이수민', 1994, 2, 8, 'F', 18, 0),
            _person('이에녹', 1997, 12, 16, 'F', 14, 30),
            _person('문지혜', 1993, 1, 26, 'F', 6, 0),
            _person('유준영', 1994, 1, 28, 'M', 11, 0),
            _person('윤주호', 1997, 1, 21, 'M', 9, 0),
            _person('조호동', 1995, 2, 23, 'M', None),
            _person('김수곤', 1996, 5, 30, 'M', 21, 5),
            _person('이정석', 1996, 7, 21, 'M', 22, 23),
            _person('심량효', 1994, 8, 2, 'M', 9, 30),
            _person('최준호', 1993, 7, 19, 'M', 8, 0),
            _person('김재민', 1997, 11, 30, 'M', 21, 20),
        ],
    },
}
