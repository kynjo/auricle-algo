import math
from music_director import MusicDirector, PHRASE_PROFILES

def _trajectory(phrase_id):
    d=MusicDirector()
    d.phrase.phrase_id=phrase_id
    d.phrase.name=phrase_id
    d.phrase.running=True
    d.phrase.intensity=1.0
    d.phrase.memory={"total_beats":16.0}
    return [d.snapshot(16.0*x) for x in (0.0,.25,.5,.75,1.0)]

def _signature(states):
    return tuple((round(s.energy,3),round(s.density,3),round(s.register_shift,2),
                  round(s.probability,3),round(s.duration_factor,3),round(s.variation,3))
                 for s in states)

def test_all_phrase_profiles_have_distinct_multidimensional_trajectories():
    signatures={pid:_signature(_trajectory(pid)) for pid in PHRASE_PROFILES}
    assert len(set(signatures.values()))==len(PHRASE_PROFILES)

def test_opening_bloom_opens_instead_of_fading_then_recovering():
    s=_trajectory("opening_bloom")
    assert s[-1].energy > s[0].energy
    assert s[-1].density > s[0].density
    assert s[-1].register_shift > s[0].register_shift

def test_tension_rise_finishes_more_intense_and_active():
    s=_trajectory("tension_rise")
    assert s[-1].tension > s[0].tension
    assert s[-1].density > s[0].density
    assert s[-1].duration_factor < s[0].duration_factor

def test_climax_release_has_internal_peak():
    s=_trajectory("climax_release")
    assert max(x.energy for x in s[1:-1]) > s[0].energy
    assert max(x.energy for x in s[1:-1]) > s[-1].energy
    assert s[-1].duration_factor > s[1].duration_factor

def test_breath_is_duration_led_not_master_fade():
    s=_trajectory("breath")
    assert max(x.duration_factor for x in s) > 1.15
    assert min(x.density for x in s) > .75

def test_accelerando_release_shortens_then_lengthens_events():
    s=_trajectory("accelerando_release")
    assert min(x.duration_factor for x in s[1:-1]) < s[0].duration_factor
    assert s[-1].duration_factor > s[0].duration_factor

def test_influence_zero_blends_dimension_to_neutral():
    d=MusicDirector(); d.phrase.phrase_id="climax_release"; d.phrase.running=True
    d.phrase.memory={"total_beats":16.0}
    d.energy_influence=0.0; d.density_influence=0.0; d.register_influence=0.0; d.probability_influence=0.0
    s=d.snapshot(8.0)
    assert math.isclose(s.energy,.72)
    assert math.isclose(s.density,1.0)
    assert math.isclose(s.register_shift,0.0)
    assert math.isclose(s.probability,1.0)
