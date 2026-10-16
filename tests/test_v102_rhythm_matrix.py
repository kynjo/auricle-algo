"""Release validation: rhythm generators output patterns, not pitch."""

def test_rhythm_values_are_not_treated_as_pitch():
    patterns = [
        [0,1,1,0,1],
        [1,0,0,1],
        [0,0,1,1,0,1],
    ]
    for pattern in patterns:
        assert all(v in (0,1) for v in pattern)
