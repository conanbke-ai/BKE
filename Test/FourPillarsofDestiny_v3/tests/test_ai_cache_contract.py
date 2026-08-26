from ai_reporter import _cache_key


def test_paid_ai_cache_key_depends_on_analysis_identity_not_local_payload_revision():
    identity = {
        'profile': {'gender': 'F', 'year': 2000, 'month': 1, 'day': 1},
        'build_matches': True,
        'pair': None,
        'group': None,
        'period': {'year': 2026, 'month': 8, 'day': 18},
    }
    a = _cache_key({'profile_local': {'old': 'layout'}}, identity)
    b = _cache_key({'profile_local': {'new': 'completely regenerated layout'}}, identity)
    assert a == b
