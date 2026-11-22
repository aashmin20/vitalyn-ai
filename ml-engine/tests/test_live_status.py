"""Three-way patient status: percentages come only from real model windows, never invented."""
from live_status import FALL, NORMAL, UNCERTAIN, StatusTracker


def tracker():
    return StatusTracker(fall_threshold=0.65)


def test_no_percentages_until_the_model_has_a_window():
    t = tracker()
    a = t.assess(alarm=False, ready=False, guarded=False, person=True)
    assert a["code"] == UNCERTAIN and a["fall_confidence"] is None and a["normal_confidence"] is None


def test_confident_normal_window_reads_normal_with_matching_percentages():
    t = tracker()
    t.add_window(0.10)
    t.add_window(0.20)
    a = t.assess(alarm=False, ready=True, guarded=False, person=True)
    assert a["code"] == NORMAL and a["label"] == "Normal bed activity"
    assert a["fall_confidence"] == 15.0 and a["normal_confidence"] == 85.0     # mean of the two real windows


def test_middle_band_is_uncertain():
    t = tracker()
    t.add_window(0.5)
    a = t.assess(alarm=False, ready=True, guarded=False, person=True)
    assert a["code"] == UNCERTAIN and a["label"].startswith("Uncertain") and a["fall_confidence"] == 50.0


def test_alarm_wins_and_keeps_the_real_model_numbers():
    t = tracker()
    t.add_window(0.9)
    a = t.assess(alarm=True, ready=True, guarded=False, person=True)
    assert a["code"] == FALL and a["label"] == "Potential fall detected" and a["fall_confidence"] == 90.0


def test_person_out_of_view_is_uncertain_without_numbers():
    t = tracker()
    t.add_window(0.1)
    t.add_window(None)                         # guarded window: no prediction, history cleared
    a = t.assess(alarm=False, ready=True, guarded=True, person=False)
    assert a["code"] == UNCERTAIN and a["fall_confidence"] is None


def test_body_low_without_a_confirmed_fall_asks_for_verification():
    t = tracker()
    t.add_window(0.1)
    a = t.assess(alarm=False, ready=True, guarded=False, person=True, body_low=True)
    assert a["code"] == UNCERTAIN and a["fall_confidence"] == 10.0


def test_smoothing_uses_only_the_last_two_windows():
    t = tracker()
    for p in (0.9, 0.1, 0.1):
        t.add_window(p)
    assert abs(t.fall_probability - 0.1) < 1e-9


def test_alarm_says_which_detector_raised_it():
    t = tracker()
    t.add_window(0.02)
    rule = t.assess(alarm=True, ready=True, guarded=False, person=True, alarm_source="context")
    assert rule["code"] == FALL and rule["raised_by"] == "context" and "movement rule" in rule["reason"]
    model = t.assess(alarm=True, ready=True, guarded=False, person=True, alarm_source="bilstm")
    assert "BiLSTM" in model["reason"]
