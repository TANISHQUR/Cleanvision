"""
Scenario tests for the littering rule. Each test builds synthetic tracked
detections frame by frame (10 fps, 1280x720) and checks what the detector reports.
Run with:  pytest tests/test_events.py -v
"""
from detector.config import EventConfig
from detector.events import Detection, LitterEventDetector

FPS = 10
W, H = 1280, 720


def person(tid, x, y=300, w=100, h=300):
    return Detection(tid, "person", "person", (x, y, x + w, y + h), 0.9)


def litter(tid, x, y, cls="bottle", size=30, conf=0.7):
    return Detection(tid, "litter", cls, (x, y, x + size, y + size), conf)


def run(frames, **kwargs):
    det = LitterEventDetector(EventConfig(verify_new_object=False), W, H, **kwargs)
    events = []
    for i, dets in enumerate(frames):
        events += det.update(i / FPS, i, dets)
    return det, events


def walk_x(t, start, speed):
    return start + speed * t


def test_person_drops_bottle_and_walks_away():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        px = walk_x(t, 200, 100)
        dets = [person(1, px)]
        if t < 3.0:
            dets.append(litter(7, px + 90, 450))          # carried in hand
        elif t >= 3.3:
            dets.append(litter(7, 500, 620))              # lying on the ground
        frames.append(dets)
    _, events = run(frames)
    assert len(events) == 1
    ev = events[0]
    assert ev.person_track_id == 1
    assert ev.waste_type == "bottle"
    assert 5.0 <= ev.detected_time <= 9.0
    assert ev.contact_time < 3.0


def test_placed_then_picked_up_is_not_littering():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        if t < 5:
            px = 500
            dets = [person(1, px)]
            if t < 2:
                dets.append(litter(3, px + 90, 450))
            else:
                dets.append(litter(3, px + 60, 610))       # set down by their feet
        else:
            px = walk_x(t - 5, 500, 120)
            dets = [person(1, px), litter(3, px + 90, 450)]  # picked up and carried off
        frames.append(dets)
    _, events = run(frames)
    assert events == []


def test_litter_already_on_ground_is_ignored():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        px = walk_x(t, 0, 110)
        dets = [person(1, px)]
        occluded = 3.5 <= t <= 4.5
        if not occluded:
            tid = 5 if t < 3.5 else 6          # tracker hands out a new ID after occlusion
            dets.append(litter(tid, 420, 610))
        frames.append(dets)
    _, events = run(frames)
    assert events == []


def test_drop_inside_bin_zone_is_not_reported():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        px = walk_x(t, 200, 100)
        dets = [person(1, px)]
        if t < 3.0:
            dets.append(litter(7, px + 90, 450))
        elif t >= 3.3:
            dets.append(litter(7, 500, 620))
        frames.append(dets)
    bin_zone = [480 / W, 600 / H, 560 / W, 670 / H]
    det, events = run(frames, bin_zones=[bin_zone])
    assert events == []
    assert ("bin_zone", 7) in det.suppressed


def test_object_carried_the_whole_time():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        px = walk_x(t, 100, 90)
        frames.append([person(1, px), litter(2, px + 90, 450)])
    _, events = run(frames)
    assert events == []


def test_person_standing_still_holding_a_bottle():
    frames = [[person(1, 500), litter(2, 590, 450)] for _ in range(12 * FPS)]
    _, events = run(frames)
    assert events == []


def test_wrapper_that_was_never_seen_in_hand():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        px = 500 if t < 3 else walk_x(t - 3, 500, 150)
        dets = [person(1, px)]
        if t >= 2.5:
            dets.append(litter(9, 540, 620, cls="wrapper", size=20))
        frames.append(dets)
    _, events = run(frames)
    assert len(events) == 1
    assert events[0].waste_type == "wrapper"
    assert events[0].person_track_id == 1


def test_same_litter_is_not_reported_twice_after_id_switch():
    frames = []
    for i in range(20 * FPS):
        t = i / FPS
        px = walk_x(t, 200, 100)
        dets = [person(1, px)] if px < W else []
        if t < 3.0:
            dets.append(litter(7, px + 90, 450))
        elif t >= 3.3:
            tid = 7 if t < 12 else 8           # ID switch later on
            if not (11.5 <= t < 12):
                dets.append(litter(tid, 500, 620))
        frames.append(dets)
    _, events = run(frames)
    assert len(events) == 1


def test_passerby_does_not_take_the_blame():
    frames = []
    for i in range(14 * FPS):
        t = i / FPS
        dets = []
        # Person 1 drops the can at t=2 and leaves slowly
        p1x = 500 if t < 2 else walk_x(t - 2, 500, -150)
        if p1x > -100:
            dets.append(person(1, p1x))
        if t < 2:
            dets.append(litter(4, 590, 450, cls="can"))
        elif t >= 2.2:
            dets.append(litter(4, 520, 620, cls="can"))
        # Person 2 walks right past the can between t=2.5 and 4
        if 2.5 <= t <= 6:
            dets.append(person(2, walk_x(t - 2.5, 350, 120)))
        frames.append(dets)
    _, events = run(frames)
    assert len(events) == 1
    assert events[0].person_track_id == 1
    assert events[0].waste_type == "can"


def test_low_confidence_new_object_is_ignored():
    frames = []
    for i in range(12 * FPS):
        t = i / FPS
        px = walk_x(t, 200, 100)
        dets = [person(1, px)]
        if t >= 3.3:
            dets.append(litter(7, 500, 620, conf=0.2))
        frames.append(dets)
    _, events = run(frames)
    assert events == []
