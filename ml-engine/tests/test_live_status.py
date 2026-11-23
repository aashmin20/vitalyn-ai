"""Fall-risk status: levels come only from real signals (BiLSTM windows, posture score), never invented."""
from fall_risk import PostureReading
from live_status import HIGH, LOW, MEDIUM, NORMAL, UNCERTAIN, StatusTracker, level_for


def tracker():
    return StatusTracker(fall_threshold=0.65)


def posture(score, horizontal=1.0, drop=1.5, reason="Lying lower than the resting position (floor level)"):
    return PostureReading(score=score, raw=score, horizontal=horizontal, drop=drop, angle=80.0, reason=reason)


def test_no_numbers_until_a_signal_exists():
    a = tracker().assess(alarm=False, ready=False, guarded=False, person=True)
    assert a["code"] == UNCERTAIN and a["risk"] is None and a["fall_confidence"] is None


def test_low_model_probability_reads_normal_with_real_percentages():
    t = tracker()
    t.add_window(0.10)
    t.add_window(0.20)
    a = t.assess(alarm=False, ready=True, guarded=False, person=True)
    assert a["code"] == NORMAL and a["risk"] == 15.0 and a["risk_source"] == "bilstm"
    assert a["fall_confidence"] == 15.0 and a["normal_confidence"] == 85.0     # mean of the two real windows


def test_bands():
    assert [level_for(x) for x in (0.1, 0.3, 0.5, 0.8)] == [NORMAL, LOW, MEDIUM, HIGH]


def test_weak_model_signal_is_shown_as_low_risk_not_ignored():
    t = tracker()
    t.add_window(0.30)
    a = t.assess(alarm=False, ready=True, guarded=False, person=True)
    assert a["code"] == LOW and a["risk"] == 30.0


def test_posture_drives_risk_when_higher_and_says_so():
    t = tracker()
    t.add_window(0.05)
    a = t.assess(alarm=False, ready=True, guarded=False, person=True, posture=posture(0.6))
    assert a["code"] == MEDIUM and a["risk"] == 60.0 and a["risk_source"] == "posture"
    assert a["fall_confidence"] == 5.0                     # BiLSTM still reported separately
    assert a["posture"]["score"] == 60.0 and "floor" in a["reason"]


def test_posture_works_before_the_model_is_ready_or_while_guarded():
    a = tracker().assess(alarm=False, ready=False, guarded=True, person=True, posture=posture(0.8))
    assert a["code"] == HIGH and a["risk"] == 80.0 and a["fall_confidence"] is None


def test_lying_at_bed_level_is_normal():
    t = tracker()
    t.add_window(0.05)
    bed = posture(0.02, horizontal=1.0, drop=0.05, reason="Lying at the resting level (bed level)")
    a = t.assess(alarm=False, ready=True, guarded=False, person=True, posture=bed)
    assert a["code"] == NORMAL and "bed level" in a["reason"]


def test_alarm_is_high_and_says_which_detector_raised_it():
    t = tracker()
    t.add_window(0.02)
    rule = t.assess(alarm=True, ready=True, guarded=False, person=True, alarm_source="context", alarm_confidence=0.66)
    assert rule["code"] == HIGH and rule["raised_by"] == "context" and "movement rule" in rule["reason"]
    assert rule["risk"] == 66.0
    p = t.assess(alarm=True, ready=True, guarded=False, person=True, alarm_source="posture", alarm_confidence=0.8)
    assert "posture" in p["reason"]
    m = t.assess(alarm=True, ready=True, guarded=False, person=True, alarm_source="bilstm")
    assert "BiLSTM" in m["reason"]


def test_person_out_of_view_is_uncertain():
    t = tracker()
    t.add_window(0.1)
    t.add_window(None)
    a = t.assess(alarm=False, ready=True, guarded=True, person=False)
    assert a["code"] == UNCERTAIN and a["risk"] is None


def test_smoothing_uses_only_the_last_two_windows():
    t = tracker()
    for p in (0.9, 0.1, 0.1):
        t.add_window(p)
    assert abs(t.fall_probability - 0.1) < 1e-9
