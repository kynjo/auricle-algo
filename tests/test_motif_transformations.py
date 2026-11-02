"""Non-destructive motif transformation behavior and musical constraints."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from motif_engine import Motif
from motif_transformations import transform_motif, transformations_for_role


@pytest.fixture
def theme():
    return Motif(
        "theme", "Theme", role="MELODY",
        notes=[0, 2, 4, 7, 9, 7, 4, 2],
        rhythm=[1, 0, 1, 1, 0, 1, 1, 0],
        velocity=[.9, 0, .6, .8, 0, .7, .75, 0], step_beats=.25,
    )


def test_transformations_never_mutate_source_and_record_lineage(theme):
    before = deepcopy(asdict(theme))
    result = transform_motif(theme, "retrograde", seed=7)
    assert asdict(theme) == before
    assert result.notes == list(reversed(theme.notes))
    assert result.rhythm == list(reversed(theme.rhythm))
    assert result.velocity == list(reversed(theme.velocity))
    assert result.parent_id == theme.id
    assert result.transformation == "retrograde"
    assert result.variations["last_transform"]["source_id"] == theme.id


@pytest.mark.parametrize("operation,amount", [
    ("transpose", 2), ("invert", 1), ("retrograde_pitch", 1),
    ("rhythm_rotate", 2), ("augment", 2), ("diminish", 2),
    ("fragment", .5), ("repeat", 3), ("accent_shift", 1),
    ("embellish", .8), ("rhythm_invert", 1),
])
def test_all_operations_return_valid_detached_motifs(theme, operation, amount):
    result = transform_motif(theme, operation, amount, "Major", 91)
    assert result is not theme
    assert result.steps >= 1
    assert len(result.rhythm) == len(result.velocity) == result.steps
    assert all(value in (0.0, 1.0) for value in result.rhythm)
    assert all(0.0 <= value <= 1.0 for value in result.velocity)
    assert all(result.velocity[i] == 0 for i, hit in enumerate(result.rhythm) if not hit)


def test_duration_transforms_and_length_transforms_are_exact(theme):
    augmented = transform_motif(theme, "augment", 2)
    diminished = transform_motif(theme, "diminish", 2)
    fragment = transform_motif(theme, "fragment", .5, seed=1)
    repeated = transform_motif(theme, "repeat", 3)
    assert augmented.step_beats == pytest.approx(.5)
    assert diminished.step_beats == pytest.approx(.125)
    assert fragment.steps == 4
    assert repeated.steps == 24


def test_transpose_is_scale_aware_and_drums_reject_pitch_operations():
    source = Motif("mel", "Mel", notes=[0, 2, 4, 7], rhythm=[1] * 4)
    result = transform_motif(source, "transpose", 1, "Major")
    assert result.notes == [2, 4, 5, 9]
    drum = Motif("dr", "Drums", role="DRUM", rhythm=[1, 0, 1, 0])
    assert "transpose" not in {key for _, key in transformations_for_role("DRUM")}
    with pytest.raises(ValueError):
        transform_motif(drum, "transpose", 1)


def test_embellish_is_deterministic_for_same_seed(theme):
    a = transform_motif(theme, "embellish", .9, "Major", 123)
    b = transform_motif(theme, "embellish", .9, "Major", 123)
    c = transform_motif(theme, "embellish", .9, "Major", 124)
    assert asdict(a) == asdict(b)
    assert asdict(a) != asdict(c)


def test_invalid_operation_and_non_finite_amount_are_rejected(theme):
    with pytest.raises(ValueError):
        transform_motif(theme, "not-a-transform")
    with pytest.raises(ValueError):
        transform_motif(theme, "transpose", float("nan"))
