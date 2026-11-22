"""Context-aware fall detector: normal bed activity stays quiet, a fast drop that settles low alerts."""
import numpy as np
import pytest

from fall_context import (
    ContextConfig, ContextualFallDetector, RuleFallDetector, body_measures, box_overlap, calibrated,
)


def person(cy: float, lying: bool = True, x: float = 300.0, conf: float = 0.9) -> np.ndarray:
    """A 17-keypoint body centred at (x, cy) in pixels. Lying = horizontal, otherwise upright."""
    k = np.zeros((17, 3))
    k[:, 2] = conf
    if lying:                                   # head left, feet right, ~30 px tall
        xs = np.linspace(x - 80, x + 80, 17)
        k[:, 0], k[:, 1] = xs, cy + np.sin(np.arange(17)) * 8
        k[5], k[6] = [x - 40, cy - 6, conf], [x - 40, cy + 6, conf]          # shoulders
        k[11], k[12] = [x + 10, cy - 6, conf], [x + 10, cy + 6, conf]        # hips (torso ~50 px)
    else:                                       # upright, ~170 px tall
        ys = np.linspace(cy - 85, cy + 85, 17)
        k[:, 0], k[:, 1] = x + np.sin(np.arange(17)) * 10, ys
        k[5], k[6] = [x - 20, cy - 50, conf], [x + 20, cy - 50, conf]
        k[11], k[12] = [x - 12, cy + 5, conf], [x + 12, cy + 5, conf]        # torso ~55 px
    return k


def run(frames, cfg=None, bed=None):
    det = ContextualFallDetector(cfg)
    return [i for i, f in enumerate(frames) if det.update(f, bed) is not None]


BED_Y, FLOOR_Y = 200.0, 420.0


def test_lying_in_bed_for_a_long_time_never_alerts():
    assert run([person(BED_Y + np.random.default_rng(1).normal(0, 2)) for _ in range(200)]) == []


def test_turning_over_and_small_movements_in_bed_never_alert():
    rng = np.random.default_rng(2)
    frames = [person(BED_Y + 15 * np.sin(i / 5) + rng.normal(0, 2), x=300 + 20 * np.sin(i / 9)) for i in range(200)]
    assert run(frames) == []


def test_sitting_up_in_bed_moves_the_body_up_and_never_alerts():
    frames = [person(BED_Y)] * 40 + [person(BED_Y - 60, lying=False)] * 60
    assert run(frames) == []


def test_slow_position_change_in_bed_does_not_alert():
    # Shifting down the bed by about one body length over ~10 s: low enough to pass the drop test,
    # but far too slow for a fall.
    frames = [person(BED_Y)] * 40 + [person(BED_Y + 50 * t / 60) for t in range(60)] + [person(BED_Y + 50)] * 40
    assert run(frames) == []


def test_known_trade_off_slow_lowering_all_the_way_to_the_floor_alerts():
    # Documented limitation of the tuned settings: ending up on the floor, even slowly over ~25 s,
    # is reported for review.
    frames = [person(BED_Y)] * 40 + [person(BED_Y + (FLOOR_Y - BED_Y) * t / 150) for t in range(150)] + [person(FLOOR_Y)] * 40
    assert len(run(frames)) == 1


def test_a_dip_that_recovers_does_not_alert():
    frames = [person(BED_Y)] * 40 + [person(FLOOR_Y)] * 3 + [person(BED_Y)] * 40
    assert run(frames) == []


def test_fast_drop_to_the_floor_that_stays_down_alerts_once():
    frames = [person(BED_Y)] * 40 + [person(BED_Y + (FLOOR_Y - BED_Y) * t / 4) for t in range(1, 5)] + [person(FLOOR_Y)] * 60
    hits = run(frames)
    assert len(hits) == 1
    assert hits[0] >= 44                       # only after the body has settled, never mid-fall


def test_fall_from_standing_alerts():
    frames = [person(300, lying=False)] * 40 + [person(FLOOR_Y)] * 40
    assert len(run(frames)) == 1


def test_no_alert_while_the_person_is_not_visible():
    frames = [person(BED_Y)] * 40 + [None] * 10 + [person(FLOOR_Y)] * 3
    assert run(frames) == []


def test_ending_up_inside_the_bed_zone_is_suppressed():
    # A camera above the bed sees the person "drop" when they lie back down. Inside the bed: not a fall.
    bed = (150.0, 150.0, 480.0, 460.0)
    frames = [person(BED_Y)] * 40 + [person(FLOOR_Y)] * 40
    assert run(frames, bed=bed) == []


def test_leaving_the_bed_zone_and_staying_down_alerts():
    bed = (150.0, 150.0, 480.0, 260.0)
    frames = [person(BED_Y)] * 40 + [person(FLOOR_Y)] * 40
    assert len(run(frames, bed=bed)) == 1


def test_cooldown_stops_repeated_alerts():
    cfg = ContextConfig(cooldown=1000)
    frames = ([person(BED_Y)] * 40 + [person(FLOOR_Y)] * 40) * 2
    assert len(run(frames, cfg)) == 1


def test_low_confidence_keypoints_are_ignored():
    assert body_measures(person(BED_Y, conf=0.1)) is None
    assert body_measures(None) is None


def test_box_overlap():
    assert box_overlap((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert box_overlap((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert box_overlap((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(0.5)


def test_calibrated_confidence_is_a_probability():
    for s in (0.0, 0.4, 0.7, 1.0):
        assert 0.0 <= calibrated(s) <= 1.0


def test_rule_detector_modes():
    frames = [person(BED_Y)] * 40 + [person(FLOOR_Y)] * 40
    ctx = RuleFallDetector("context")
    results = [r for r in (ctx.update(f) for f in frames) if r is not None]
    assert len(results) == 1 and results[0][1] == "context" and 0 <= results[0][0] <= 1
    legacy = RuleFallDetector("legacy")
    assert all(legacy.update(f) is None for f in [person(BED_Y)] * 50)     # lying the whole time
    assert RuleFallDetector("nonsense").mode == "context"
