from music_director import MusicDirector

ROLES=("DRUM","BASS","MELODY","CHORD","PAD")

def director(phrase="opening_bloom", progress=.6):
    d=MusicDirector()
    d.phrase.phrase_id=phrase
    d.phrase.running=True
    d.phrase.intensity=1.0
    d.phrase.memory={"total_beats":16.0}
    return d,d.snapshot(16.0*progress)

def signature(s):
    return (round(s.energy,3),round(s.density,3),round(s.register_shift,3),
            round(s.probability,3),round(s.duration_factor,3),round(s.variation,3),s.activity_mode)

def test_same_phrase_has_distinct_role_interpretations():
    d,state=director("tension_rise",.75)
    sigs={role:signature(d.role_state(role,state)) for role in ROLES}
    assert len(set(sigs.values()))==len(ROLES)

def test_bass_stays_more_grounded_than_melody():
    d,state=director("opening_bloom",1.0)
    bass=d.role_state("BASS",state); melody=d.role_state("MELODY",state)
    assert abs(bass.register_shift) < abs(melody.register_shift)
    assert bass.variation < melody.variation

def test_chord_and_pad_use_harmonic_activity_not_note_deletion_semantics():
    d,state=director("breath",.7)
    chord=d.role_state("CHORD",state); pad=d.role_state("PAD",state)
    assert chord.activity_mode=="harmonic" and pad.activity_mode=="harmonic"
    assert chord.duration_factor > 1.0 and pad.duration_factor > chord.duration_factor
    assert pad.variation < chord.variation

def test_accelerando_is_strongest_in_rhythm_section():
    d,state=director("accelerando_release",.6)
    drum=d.role_state("DRUM",state)
    chord=d.role_state("CHORD",state); pad=d.role_state("PAD",state)
    # Rhythmic roles receive much stronger variation/shortening while
    # harmonic roles deliberately preserve attacks.
    assert drum.duration_factor > chord.duration_factor
    assert drum.variation > chord.variation

def test_phrase_role_matrix_changes_same_role_across_phrases():
    signatures=[]
    for phrase in ("opening_bloom","tension_rise","climax_release","breath","accelerando_release"):
        d,state=director(phrase,.6)
        signatures.append(signature(d.role_state("MELODY",state)))
    assert len(set(signatures))==5
