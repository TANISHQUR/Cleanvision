"""
Littering event logic.

This module has no dependency on YOLO, OpenCV or a GPU. It receives tracked
detections for each frame and decides when a littering event has happened,
which makes it easy to unit test and to explain.

The rule, in plain words:

1. A litter object gets a "holder": the person it was near while it was moving
   (being carried), or the person who was near that spot when the object first
   appeared (small wrappers are often invisible while in someone's hand).
2. The object becomes stationary (it has landed).
3. It stays stationary for `linger_s` seconds while its holder has walked
   away or left the frame.
4. It is not inside a dustbin zone and hasn't already been reported.

Objects that were already lying there before anyone came near are marked
"pre-existing" and never trigger an event.
"""
from __future__ import annotations

import math
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field

from .config import EventConfig

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


@dataclass
class Detection:
    track_id: int
    kind: str          # "person" or "litter"
    cls_name: str
    box: Box
    conf: float


@dataclass
class LitterEvent:
    event_id: str
    object_track_id: int
    person_track_id: int | None
    waste_type: str
    confidence: float
    frame_index: int
    detected_time: float       # seconds into the video when the event fired
    release_time: float        # when the object came to rest
    contact_time: float        # last time the holder was seen with the object
    object_box: Box
    person_box: Box | None
    contact_frame_index: int
    verified_new: bool | None = None   # filled in by the pipeline's background check

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "object_track_id": self.object_track_id,
            "person_track_id": self.person_track_id,
            "waste_type": self.waste_type,
            "confidence": round(self.confidence, 3),
            "frame_index": self.frame_index,
            "detected_time": round(self.detected_time, 2),
            "release_time": round(self.release_time, 2),
            "contact_time": round(self.contact_time, 2),
            "object_box": [round(v, 1) for v in self.object_box],
            "person_box": [round(v, 1) for v in self.person_box] if self.person_box else None,
            "contact_frame_index": self.contact_frame_index,
            "verified_new": self.verified_new,
        }


# ---------------------------------------------------------------- geometry

def center(b: Box) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def expand(b: Box, margin: float) -> Box:
    w, h = b[2] - b[0], b[3] - b[1]
    return (b[0] - w * margin, b[1] - h * margin, b[2] + w * margin, b[3] + h * margin)


def point_in(p: tuple[float, float], b: Box) -> bool:
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def boxes_overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def point_box_distance(p: tuple[float, float], b: Box) -> float:
    dx = max(b[0] - p[0], 0.0, p[0] - b[2])
    dy = max(b[1] - p[1], 0.0, p[1] - b[3])
    return math.hypot(dx, dy)


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def zone_to_px(zone: list[float], w: int, h: int) -> Box:
    return (zone[0] * w, zone[1] * h, zone[2] * w, zone[3] * h)


# ------------------------------------------------------------------ state

@dataclass
class _Person:
    track_id: int
    box: Box
    last_seen: float
    last_frame: int
    history: deque = field(default_factory=lambda: deque(maxlen=120))  # (t, box)


@dataclass
class _Object:
    track_id: int
    first_seen: float
    last_seen: float
    history: deque = field(default_factory=lambda: deque(maxlen=300))   # (t, center, box)
    votes: Counter = field(default_factory=Counter)
    conf_sum: float = 0.0
    conf_n: int = 0
    pre_existing: bool = False
    holder_id: int | None = None
    holder_confirmed: bool = False
    candidate_id: int | None = None
    candidate_time: float = 0.0
    contacts: deque = field(default_factory=lambda: deque(maxlen=600))  # (t, frame) holder was near
    stationary_since: float | None = None
    done: bool = False

    def contact_before(self, t_limit: float) -> tuple[float, int]:
        """Last moment the holder was with the object before it came to rest."""
        before = [c for c in self.contacts if c[0] < t_limit]
        if before:
            return before[-1]
        return self.contacts[0] if self.contacts else (self.first_seen, 0)

    @property
    def box(self) -> Box:
        return self.history[-1][2]

    @property
    def waste_type(self) -> str:
        return self.votes.most_common(1)[0][0] if self.votes else "unknown"

    @property
    def mean_conf(self) -> float:
        return self.conf_sum / self.conf_n if self.conf_n else 0.0


# --------------------------------------------------------------- detector

class LitterEventDetector:
    def __init__(self, cfg: EventConfig, frame_w: int, frame_h: int,
                 bin_zones: list[list[float]] | None = None,
                 ignore_zones: list[list[float]] | None = None):
        self.cfg = cfg
        self.w, self.h = frame_w, frame_h
        self.bin_zones = [zone_to_px(z, frame_w, frame_h) for z in (bin_zones or [])]
        self.ignore_zones = [zone_to_px(z, frame_w, frame_h) for z in (ignore_zones or [])]
        self.persons: dict[int, _Person] = {}
        self.objects: dict[int, _Object] = {}
        self.reported: list[tuple[float, Box]] = []
        self.suppressed: list[tuple[str, int]] = []   # (reason, object track id), useful for debugging
        # Recently forgotten objects that were pre-existing or already reported.
        # A new track at the same spot is almost always the same object with a new ID.
        self.ghosts: deque = deque(maxlen=200)   # (last_seen, box, pre_existing, done)

    # -- helpers -----------------------------------------------------------
    def _near(self, obj_box: Box, person_box: Box) -> bool:
        return boxes_overlap(obj_box, expand(person_box, self.cfg.near_margin))

    def _nearest_person(self, obj_box: Box, candidates: list[tuple[int, Box]]) -> tuple[int, Box] | None:
        c = center(obj_box)
        best = None
        best_d = float("inf")
        for pid, pbox in candidates:
            if self._near(obj_box, pbox):
                d = point_box_distance(c, pbox)
                if d < best_d:
                    best, best_d = (pid, pbox), d
        return best

    def _recent_person_boxes(self, t: float) -> list[tuple[int, Box]]:
        out = []
        for p in self.persons.values():
            for pt, pbox in p.history:
                if t - pt <= self.cfg.assoc_window_s:
                    out.append((p.track_id, pbox))
        return out

    def _is_stationary(self, obj: _Object, t: float) -> tuple[bool, float]:
        win = self.cfg.stationary_window_s
        pts = [(pt, c) for pt, c, _ in obj.history if t - pt <= win]
        if len(pts) < 3 or (pts[-1][0] - pts[0][0]) < 0.6 * win:
            return False, t
        xs = sorted(c[0] for _, c in pts)
        ys = sorted(c[1] for _, c in pts)
        mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
        tol = self.cfg.stationary_tol * self.h
        if all(math.hypot(c[0] - mx, c[1] - my) <= tol for _, c in pts):
            return True, pts[0][0]
        return False, t

    def _in_zone(self, box: Box, zones: list[Box]) -> bool:
        c = center(box)
        return any(point_in(c, z) for z in zones)

    def _inherit_from_lost(self, box: Box, t: float, seen_ids: set[int]) -> tuple[bool, bool] | None:
        for o in self.objects.values():
            if o.track_id not in seen_ids and (o.pre_existing or o.done) and iou(o.box, box) >= 0.3:
                return o.pre_existing, o.done
        for gt, gbox, pre, done in self.ghosts:
            if t - gt <= 60 and iou(gbox, box) >= 0.3:
                return pre, done
        return None

    def _moved_from_start(self, obj: _Object) -> float:
        c0 = obj.history[0][1]
        c1 = obj.history[-1][1]
        return math.hypot(c1[0] - c0[0], c1[1] - c0[1])

    # -- main entry --------------------------------------------------------
    def update(self, t: float, frame_index: int, detections: list[Detection]) -> list[LitterEvent]:
        cfg = self.cfg

        # 1. people
        current_people: list[tuple[int, Box]] = []
        for d in detections:
            if d.kind != "person":
                continue
            p = self.persons.get(d.track_id)
            if p is None:
                p = self.persons[d.track_id] = _Person(d.track_id, d.box, t, frame_index)
            p.box, p.last_seen, p.last_frame = d.box, t, frame_index
            p.history.append((t, d.box))
            current_people.append((d.track_id, d.box))

        # 2. litter objects
        seen_ids = {d.track_id for d in detections if d.kind == "litter"}
        for d in detections:
            if d.kind != "litter" or self._in_zone(d.box, self.ignore_zones):
                continue
            obj = self.objects.get(d.track_id)
            if obj is None:
                if d.conf < cfg.min_object_conf:
                    continue
                obj = self.objects[d.track_id] = _Object(d.track_id, t, t)
                inherited = self._inherit_from_lost(d.box, t, seen_ids)
                if inherited is not None:
                    obj.pre_existing, obj.done = inherited
                    obj.history.append((t, center(d.box), d.box))
                    obj.last_seen = t
                    continue
                # Link a brand-new object to whoever was just near this spot.
                hit = self._nearest_person(d.box, self._recent_person_boxes(t))
                if hit:
                    obj.holder_id, obj.holder_confirmed = hit[0], True
                    obj.contacts.append((t, frame_index))
                else:
                    obj.pre_existing = True

            obj.last_seen = t
            obj.history.append((t, center(d.box), d.box))
            obj.votes[d.cls_name] += d.conf
            obj.conf_sum += d.conf
            obj.conf_n += 1

            stationary, since = self._is_stationary(obj, t)
            if stationary:
                if obj.stationary_since is None:
                    obj.stationary_since = since
            else:
                obj.stationary_since = None

            hit = self._nearest_person(d.box, current_people)
            if hit is None:
                obj.candidate_id = None
                continue
            pid = hit[0]

            if obj.pre_existing:
                # Someone picked up litter that was already there. Treat it as theirs now.
                if self._moved_from_start(obj) > 3 * cfg.stationary_tol * self.h:
                    obj.pre_existing = False
                    obj.holder_id, obj.holder_confirmed = pid, True
                    obj.contacts.append((t, frame_index))
                continue

            if pid == obj.holder_id:
                obj.contacts.append((t, frame_index))
            elif obj.stationary_since is None:
                # A different person is near a MOVING object: they may have taken it.
                # Require sustained contact so a passer-by doesn't steal ownership.
                if obj.candidate_id != pid:
                    obj.candidate_id, obj.candidate_time = pid, t
                elif t - obj.candidate_time >= cfg.min_contact_s:
                    obj.holder_id, obj.holder_confirmed = pid, True
                    obj.contacts.append((t, frame_index))
                    obj.candidate_id = None

        # 3. decide
        events: list[LitterEvent] = []
        for obj in self.objects.values():
            if obj.done or obj.pre_existing or not obj.holder_confirmed:
                continue
            if obj.stationary_since is None or t - obj.last_seen > 0.5:
                continue
            if t - obj.stationary_since < cfg.linger_s:
                continue

            holder = self.persons.get(obj.holder_id)
            if holder is not None and t - holder.last_seen < cfg.absent_s:
                ph = max(holder.box[3] - holder.box[1], 1.0)
                if point_box_distance(center(obj.box), holder.box) / ph < cfg.separation:
                    continue   # holder is still standing next to it

            obj.done = True
            if self._in_zone(obj.box, self.bin_zones):
                self.suppressed.append(("bin_zone", obj.track_id))
                continue
            if any(t - rt <= cfg.dedupe_s and iou(rb, obj.box) >= cfg.dedupe_iou for rt, rb in self.reported):
                self.suppressed.append(("duplicate", obj.track_id))
                continue

            self.reported.append((t, obj.box))
            contact_t, contact_frame = obj.contact_before(obj.stationary_since)
            events.append(LitterEvent(
                event_id=uuid.uuid4().hex[:12],
                object_track_id=obj.track_id,
                person_track_id=obj.holder_id,
                waste_type=obj.waste_type,
                confidence=obj.mean_conf,
                frame_index=frame_index,
                detected_time=t,
                release_time=obj.stationary_since,
                contact_time=contact_t,
                object_box=obj.box,
                person_box=holder.box if holder else None,
                contact_frame_index=contact_frame,
            ))

        # 4. forget stale tracks
        timeout = cfg.track_timeout_s
        for o in self.objects.values():
            if t - o.last_seen > timeout and (o.pre_existing or o.done):
                self.ghosts.append((o.last_seen, o.box, o.pre_existing, o.done))
        self.objects = {k: o for k, o in self.objects.items() if t - o.last_seen <= timeout}
        # Keep people a bit longer: an object's holder may be needed after they leave.
        self.persons = {k: p for k, p in self.persons.items() if t - p.last_seen <= timeout + cfg.linger_s + 5}
        return events
