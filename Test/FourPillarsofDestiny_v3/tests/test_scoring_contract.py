from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _literal_assignment(name: str):
    tree = ast.parse((ROOT / 'scoring.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f'{name} assignment not found')


def test_love_weights_sum_one():
    weights = _literal_assignment('LOVE_WEIGHTS')
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert set(weights) == {
        'element_need', 'spouse_palace', 'spouse_star', 'stem_daymaster',
        'branch_network', 'month_life', 'conflict_buffer',
    }


def test_friend_weights_sum_one_and_has_no_romance_axes():
    weights = _literal_assignment('FRIEND_WEIGHTS')
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert set(weights) == {
        'element_need', 'stem_communication', 'branch_network',
        'friend_ten_gods', 'month_social', 'conflict_buffer',
    }
    assert 'spouse_palace' not in weights
    assert 'spouse_star' not in weights
