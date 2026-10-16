from generators import quantize_to_scale, scale_intervals


def test_quantize_to_scale_keeps_pitch_class():
    for note in range(36, 96):
        q = int(quantize_to_scale(note, 0, "Major"))
        assert q % 12 in set(scale_intervals("Major"))


def test_major_scale_contains_expected_intervals():
    assert scale_intervals("Major")[:7] == [0,2,4,5,7,9,11]


def test_voice_leading_reset():
    from voice_leading import VoiceLeading
    v = VoiceLeading()
    v.resolve_pitch("a", 60)
    v.reset()
    assert v.previous == {}
