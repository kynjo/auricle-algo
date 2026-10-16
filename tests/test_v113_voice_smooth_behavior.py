from voice_leading import VoiceLeading

def test_voice_smooth_range_and_direction():
    free = VoiceLeading(smoothness=0.0)
    smooth = VoiceLeading(smoothness=1.0)
    assert free.smoothness == 0.0
    assert smooth.smoothness == 1.0


def test_voice_smooth_is_clamped():
    assert VoiceLeading(smoothness=-5).smoothness == 0.0
    assert VoiceLeading(smoothness=5).smoothness == 1.0
