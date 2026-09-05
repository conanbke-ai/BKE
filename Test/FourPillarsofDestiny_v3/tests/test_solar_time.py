from datetime import datetime

from bazi_engine import calculate_chart
from models import BirthProfile
from solar_time import calculate_time_correction, resolve_birth_location


def test_seoul_1994_boundary_differs_by_manse_method():
    selected, meta = calculate_time_correction(
        country_code='KR',
        city='서울특별시',
        civil_datetime=datetime(1994, 12, 7, 5, 30),
        time_known=True,
        mode='true_solar',
    )

    assert meta['location_resolved'] is True
    assert meta['branch_by_method']['civil'] == '卯'
    assert meta['branch_by_method']['local_mean'] == '寅'
    assert meta['branch_by_method']['true_solar'] == '卯'
    assert meta['boundary_warning'] is True
    assert '인시/묘시' in meta['warning']
    assert selected.hour == 5
    assert 0 <= selected.minute < 30


def test_same_birth_can_use_local_mean_without_generating_second_report():
    selected, meta = calculate_time_correction(
        country_code='KR',
        city='서울',
        civil_datetime=datetime(1994, 12, 7, 5, 30),
        time_known=True,
        mode='local_mean',
    )

    assert meta['mode'] == 'local_mean'
    assert meta['selected_branch'] == '寅'
    assert selected.hour == 4


def test_chart_uses_true_solar_time_as_default_and_keeps_metadata():
    profile = BirthProfile(
        name='경계 테스트', gender='F', calendar_type='solar',
        year=1994, month=12, day=7, hour=5, minute=30,
        country_code='KR', country='대한민국', city='서울특별시',
    )
    chart = calculate_chart(profile)

    assert chart.hour_pillar.endswith('卯')
    assert chart.time_correction['boundary_warning'] is True
    assert chart.time_correction['calculation_version'].startswith('true-solar-v1')


def test_historical_dst_is_read_from_timezone_database():
    _, meta = calculate_time_correction(
        country_code='KR',
        city='서울',
        civil_datetime=datetime(1988, 6, 15, 12, 0),
        time_known=True,
        mode='true_solar',
    )

    assert meta['timezone_id'] == 'Asia/Seoul'
    assert meta['utc_offset_hours'] == 10.0
    assert meta['dst_offset_hours'] == 1.0


def test_korean_birthplace_resolver_handles_bucheon():
    location = resolve_birth_location('KR', '경기도 부천시')

    assert location is not None
    assert location.name == '부천시'
    assert location.timezone_id == 'Asia/Seoul'
    assert 126.7 < location.longitude < 126.9


def test_unknown_city_falls_back_to_recorded_clock_time_with_warning_metadata():
    civil = datetime(1994, 12, 7, 5, 30)
    selected, meta = calculate_time_correction(
        country_code='KR',
        city='없는도시이름',
        civil_datetime=civil,
        time_known=True,
        mode='true_solar',
    )

    assert selected == civil
    assert meta['location_resolved'] is False
    assert meta['applied'] is False
    assert meta['selected_branch'] == '卯'
    assert meta['location_warning']
