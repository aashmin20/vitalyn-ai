"""Posture risk: floor-level lying raises the score, bed-level lying and upright activity do not."""
import numpy as np

from fall_risk import FloorPostureMonitor


def body(shoulder_y, hip_y, x_shift=0.0, horizontal=False, conf=0.9):
    """A simple 17-keypoint figure. Upright: hips below shoulders. Horizontal: hips beside shoulders."""
    k = np.zeros((17, 3))
    k[:, 2] = conf
    if horizontal:
        sh = [(200, shoulder_y), (200, shoulder_y + 10)]
        hp = [(300, shoulder_y), (300, shoulder_y + 10)]
        k[0] = (150, shoulder_y, conf)
        k[[1, 2, 3, 4]] = [(145, shoulder_y - 5, conf)] * 4
        k[[7, 8, 9, 10]] = [(230, shoulder_y + 5, conf)] * 4
        k[[13, 14, 15, 16]] = [(380, shoulder_y + 5, conf), (380, shoulder_y + 15, conf),
                               (450, shoulder_y + 5, conf), (450, shoulder_y + 15, conf)]
    else:
        sh = [(280, shoulder_y), (320, shoulder_y)]
        hp = [(285, hip_y), (315, hip_y)]
        k[0] = (300, shoulder_y - 40, conf)
        k[[1, 2, 3, 4]] = [(300, shoulder_y - 45, conf)] * 4
        k[[7, 8, 9, 10]] = [(300, (shoulder_y + hip_y) / 2, conf)] * 4
        k[[13, 14, 15, 16]] = [(290, hip_y + 60, conf), (310, hip_y + 60, conf),
                               (290, hip_y + 120, conf), (310, hip_y + 120, conf)]
    k[5, :2], k[6, :2] = sh
    k[11, :2], k[12, :2] = hp
    k[:, 0] += x_shift
    return k


def run(monitor, frames):
    out = None
    for f in frames:
        out = monitor.update(f)
    return out


def test_standing_then_lying_on_the_floor_reaches_high():
    m = FloorPostureMonitor()
    run(m, [body(150, 250)] * 40)                      # standing, torso 100 px
    r = run(m, [body(420, 0, horizontal=True)] * 18)    # on the floor: shoulders 2.7 torso-lengths lower
    assert r.score >= 0.75 and "floor" in r.reason
    assert r.horizontal == 1.0 and r.drop > 2


def test_slow_lie_down_still_counts():
    m = FloorPostureMonitor()
    run(m, [body(150, 250)] * 40)
    for y in np.linspace(150, 420, 30):                # 5 s descent: the context rule would call this slow
        m.update(body(float(y), float(y) + 100) if y < 380 else body(float(y), 0, horizontal=True))
    r = run(m, [body(420, 0, horizontal=True)] * 12)
    assert r.score >= 0.75


def test_lying_in_bed_at_the_resting_level_stays_low():
    m = FloorPostureMonitor()
    r = run(m, [body(300, 0, horizontal=True, x_shift=float(i % 5)) for i in range(120)])
    assert r.score < 0.1 and "bed level" in r.reason


def test_bending_down_and_back_up_does_not_stay_raised():
    m = FloorPostureMonitor()
    run(m, [body(150, 250)] * 40)
    run(m, [body(230, 300)] * 4)                       # brief bend (not horizontal, < 1 torso lower)
    r = run(m, [body(150, 250)] * 12)
    assert r.score < 0.25


def test_resting_level_is_frozen_while_on_the_floor():
    m = FloorPostureMonitor()
    run(m, [body(150, 250)] * 40)
    r = run(m, [body(420, 0, horizontal=True)] * 200)   # 33 s on the floor: must not become "normal"
    assert r.score >= 0.75


def test_getting_up_releases_the_risk():
    m = FloorPostureMonitor()
    run(m, [body(150, 250)] * 40)
    run(m, [body(420, 0, horizontal=True)] * 30)
    r = run(m, [body(150, 250)] * 30)
    assert r.score < 0.1


def test_no_person_decays_slowly_and_reports_it():
    m = FloorPostureMonitor()
    run(m, [body(150, 250)] * 40)
    run(m, [body(420, 0, horizontal=True)] * 20)
    before = m.score
    r = m.update(None)
    assert 0 < r.score < before and r.drop is None and "not clearly visible" in r.reason


def test_needs_a_resting_level_first():
    r = FloorPostureMonitor().update(body(420, 0, horizontal=True))
    assert r.score == 0.0 and r.drop is None
