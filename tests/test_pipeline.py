"""
Runs the full pipeline (video reading, event rule, background check, evidence
writing) on a synthetic video. A scripted tracker stands in for YOLO so the
test is fast and deterministic.
"""
import json

import cv2
import numpy as np

from detector.config import Config
from detector.events import Detection
from detector.pipeline import Pipeline

FPS = 10
W, H = 640, 360


def person_box(t):
    x = 60 + 50 * t
    return (x, 120, x + 50, 300)


def bottle_box(t, drop_t=2.0):
    if t < drop_t:
        px = person_box(t)[0]
        return (px + 45, 200, px + 60, 225)
    return (175, 300, 190, 325)


class ScriptedTracker:
    """Returns detections for a known scenario, like YOLO + ByteTrack would."""

    def __init__(self, bottle_visible_from=0.0):
        self.i = 0
        self.bottle_visible_from = bottle_visible_from

    def __call__(self, frame):
        t = self.i / FPS
        self.i += 1
        dets = []
        pb = person_box(t)
        if pb[0] < W:
            dets.append(Detection(1, "person", "person", pb, 0.9))
        if t >= self.bottle_visible_from:
            dets.append(Detection(5, "litter", "bottle", bottle_box(t), 0.8))
        return dets


def write_video(path, seconds, old_litter=False):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    rng = np.random.default_rng(0)
    for i in range(int(seconds * FPS)):
        t = i / FPS
        frame = np.full((H, W, 3), 90, np.uint8)
        frame += rng.integers(0, 4, frame.shape, dtype=np.uint8)
        x1, y1, x2, y2 = (int(v) for v in person_box(t))
        cv2.rectangle(frame, (x1, y1), (x2, y2), (40, 60, 160), -1)
        box = (175, 300, 190, 325) if old_litter else bottle_box(t)
        bx1, by1, bx2, by2 = (int(v) for v in box)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (240, 240, 240), -1)
        vw.write(frame)
    vw.release()


def make_cfg(tmp_path):
    cfg = Config()
    cfg.evidence.output_dir = str(tmp_path / "runs")
    cfg.evidence.pre_s = 5
    cfg.evidence.post_s = 1
    cfg.evidence.fps = 10
    return cfg


def test_new_litter_produces_evidence(tmp_path):
    video = tmp_path / "drop.mp4"
    write_video(video, 10)
    summary = Pipeline(make_cfg(tmp_path), tracker=ScriptedTracker()).run(str(video))

    assert len(summary.events) == 1, summary.suppressed
    ev = summary.events[0]
    assert ev["waste_type"] == "bottle"
    assert ev["person_track_id"] == 1
    assert ev["verified_new"] is True
    assert ev["camera_id"] == "CAM-01"

    folder = tmp_path / "runs" / summary.run_id / ev["event_id"]
    for name in ("clip.mp4", "contact.jpg", "scene.jpg", "event.json"):
        assert (folder / name).exists(), name
    cap = cv2.VideoCapture(str(folder / "clip.mp4"))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(errors="ignore")
    cap.release()
    assert frames >= 40
    assert fourcc.lower() in ("avc1", "h264")      # browser-playable
    assert json.loads((folder / "event.json").read_text())["event_id"] == ev["event_id"]
    assert (tmp_path / "runs" / summary.run_id / "summary.json").exists()


def test_litter_that_was_already_there_is_suppressed(tmp_path):
    # The bottle lies on the ground the whole time, but the detector only
    # notices it when the person walks past (a missed detection earlier).
    video = tmp_path / "old.mp4"
    write_video(video, 10, old_litter=True)

    class OldBottleTracker(ScriptedTracker):
        def __call__(self, frame):
            t = self.i / FPS
            self.i += 1
            dets = []
            pb = person_box(t)
            if pb[0] < W:
                dets.append(Detection(1, "person", "person", pb, 0.9))
            if t >= 2.4:
                dets.append(Detection(5, "litter", "bottle", (175, 300, 190, 325), 0.8))
            return dets

    summary = Pipeline(make_cfg(tmp_path), tracker=OldBottleTracker()).run(str(video))
    assert summary.events == []
    assert any(s["reason"] == "already_there" for s in summary.suppressed)
