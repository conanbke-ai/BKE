from progress_tracker import _initial_stages


def test_group_members_are_total_including_user():
    stages = _initial_stages({'group_members': 15})
    pairwise = next(stage for stage in stages if stage.key == 'group_pairwise')
    assert pairwise.units == 105


def test_no_group_stage_for_user_only():
    stages = _initial_stages({'group_members': 1})
    assert not any(stage.key == 'group_pairwise' for stage in stages)


def test_string_false_does_not_enable_optional_initial_stages():
    stages = _initial_stages({'build_matches': 'false', 'include_pair': 'false', 'group_members': 1})
    keys = {stage.key for stage in stages}
    assert 'auto_scan' not in keys
    assert 'pair_collect' not in keys
    assert 'group_pairwise' not in keys


def test_group_15_baseline_is_not_underestimated():
    from progress_tracker import _group_stages
    stages = _group_stages({'members': 15})
    assert sum(stage.expected for stage in stages) >= 60
    collect = next(stage for stage in stages if stage.key == 'collect')
    assert collect.expected >= 60


def test_test_profile_does_not_learn_runtime_metrics():
    from progress_tracker import create_job
    job = create_job('group', {'members': 15, 'timing_profile': 'live', 'disable_timing_learning': True})
    assert job.record_metrics is False


def test_live_profile_can_learn_runtime_metrics():
    from progress_tracker import create_job
    job = create_job('pair', {'timing_profile': 'live'})
    assert job.record_metrics is True


def test_runtime_metric_namespace_resets_old_contaminated_history():
    from progress_tracker import _total_metric_key
    assert _total_metric_key('group', {'members': 15}).startswith('live_v2:')


def test_initial_eta_expands_with_pair_and_group_scope():
    from progress_tracker import estimate

    base = estimate('initial', {
        'birth_year': 2000,
        'build_matches': False,
        'include_pair': False,
        'group_members': 0,
    })['expected_seconds']['seconds']
    expanded = estimate('initial', {
        'birth_year': 2000,
        'build_matches': False,
        'include_pair': True,
        'group_members': 5,
    })['expected_seconds']['seconds']

    assert expanded > base
