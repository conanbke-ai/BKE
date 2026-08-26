from storage import canonical_profile_identity


def base_profile(**overrides):
    row = {
        'name': '표시이름',
        'gender': 'F',
        'calendar_type': 'solar',
        'year': 2000,
        'month': 1,
        'day': 1,
        'time_known': True,
        'hour': 12,
        'minute': 0,
        'is_leap_month': False,
        'country_code': 'KR',
    }
    row.update(overrides)
    return row


def test_false_string_does_not_become_true():
    identity = canonical_profile_identity(base_profile(time_known='false', hour=5, minute=30))
    assert identity['time_known'] is False
    assert identity['hour'] is None
    assert identity['minute'] is None


def test_solar_ignores_stale_leap_month_value():
    a = canonical_profile_identity(base_profile(is_leap_month=False))
    b = canonical_profile_identity(base_profile(is_leap_month='true'))
    assert a == b


def test_korea_ignores_city_for_cache_identity():
    a = canonical_profile_identity(base_profile(city='서울'))
    b = canonical_profile_identity(base_profile(city='부산'))
    assert a == b
