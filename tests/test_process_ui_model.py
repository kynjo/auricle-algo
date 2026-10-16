from auricle_core import Process


def test_process_has_no_required_universal_ui_parameter():
    # amount remains only as a backward-compatible serialized field; GUI exposes
    # it only under process-specific names where it has semantic meaning.
    for kind in ["Clock Divide", "Clock Multiply", "Memory", "Delay", "Feedback", "Parameter Modulation"]:
        p = Process(kind, "pitch", 0.37, {})
        assert p.amount == 0.37


def test_process_specific_parameters_are_independent():
    delay = Process("Delay", "pitch", 0.1, {"delay": 7, "repeats": 5, "feedback": 0.81, "mix": 0.42, "decay": 0.63})
    assert delay.parameters["delay"] == 7
    assert delay.parameters["repeats"] == 5
    assert delay.parameters["feedback"] == 0.81
    assert delay.parameters["mix"] == 0.42
    assert delay.parameters["decay"] == 0.63
