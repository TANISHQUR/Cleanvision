"""
Video pipeline: read frames -> YOLO + ByteTrack -> littering rule -> evidence -> backend.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .api_client import ApiClient
from .config import Config
from .events import Detection, LitterEvent, LitterEventDetector, boxes_overlap, expand
from .evidence import EvidenceFiles, EvidenceRecorder

log = logging.getLogger(__name__)


# ------------------------------------------------------------- detection

class Tracker:
    """Wraps one or two YOLO models and returns tracked person/litter detections."""

    def __init__(self, cfg: Config):
        from ultralytics import YOLO  # imported here so the rest of the package works without it

        m = cfg.model
        self.m = m
        self.model = YOLO(m.weights)
        names = self.model.names
        self.litter_ids = [i for i, n in names.items() if n in m.litter_classes]
        if not self.litter_ids:
            raise ValueError(f"None of {m.litter_classes} exist in {m.weights}. Model classes: {list(names.values())}")

        self.person_model = None
        person_ids = [i for i, n in names.items() if n == m.person_class]
        if m.person_weights:
            self.person_model = YOLO(m.person_weights)
            pn = self.person_model.names
            self.person_ids_2 = [i for i, n in pn.items() if n == m.person_class]
            person_ids = []
        elif not person_ids:
            raise ValueError(
                f"'{m.person_class}' is not a class in {m.weights}. Either train with a person class "
                "or set model.person_weights to a COCO model such as yolo11n.pt."
            )
        self.person_ids = person_ids
        self.classes = self.litter_ids + self.person_ids
        self.precision_args = self._precision_args()
        log.info("Litter classes: %s", [names[i] for i in self.litter_ids])

    def _precision_args(self) -> dict:
        """FP16 on GPU. Newer Ultralytics renamed `half` to `quantize`, so support both."""
        if not self.m.half or str(self.m.device) == "cpu":
            return {}
        from ultralytics.cfg import DEFAULT_CFG_DICT

        return {"quantize": 16} if "quantize" in DEFAULT_CFG_DICT else {"half": True}

    def _track(self, model, frame, classes):
        m = self.m
        res = model.track(frame, persist=True, conf=m.conf, iou=m.iou, imgsz=m.imgsz,
                          classes=classes, tracker=m.tracker, device=m.device,
                          verbose=False, **self.precision_args)[0]
        if res.boxes is None or res.boxes.id is None:
            return []
        xyxy = res.boxes.xyxy.cpu().numpy()
        ids = res.boxes.id.int().cpu().tolist()
        cls = res.boxes.cls.int().cpu().tolist()
        conf = res.boxes.conf.cpu().tolist()
        return [(ids[k], model.names[cls[k]], cls[k], tuple(float(v) for v in xyxy[k]), conf[k])
                for k in range(len(ids))]

    def __call__(self, frame: np.ndarray) -> list[Detection]:
        out = []
        for tid, name, cid, box, conf in self._track(self.model, frame, self.classes):
            kind = "person" if cid in self.person_ids else "litter"
            out.append(Detection(tid, kind, name, box, conf))
        if self.person_model is not None:
            for tid, name, _, box, conf in self._track(self.person_model, frame, self.person_ids_2):
                out.append(Detection(100000 + tid, "person", name, box, conf))
        return out


# ------------------------------------------------- "was it already there?"

class SceneHistory:
    """Grayscale snapshots every 0.5 s, used to check whether litter was already lying there."""

    def __init__(self, frame_w: int, frame_h: int, keep_s: float = 30, every_s: float = 0.5):
        self.scale = min(1.0, 640 / frame_w)
        self.every = every_s
        self.snaps: deque = deque(maxlen=int(keep_s / every_s))
        self._last = -1e9

    def _gray(self, frame):
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(g, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)

    def add(self, t: float, frame: np.ndarray, dets: list[Detection]) -> None:
        if t - self._last >= self.every:
            people = [d.box for d in dets if d.kind == "person"]
            self.snaps.append((t, self._gray(frame), people))
            self._last = t

    def was_already_there(self, ev: LitterEvent, frame: np.ndarray, max_diff: float) -> bool | None:
        """True = the spot looked the same before anyone arrived, so this is old litter.
        False = the spot changed, so the object is new. None = no clean reference frame."""
        region = expand(ev.object_box, 0.2)
        cutoff = min(ev.contact_time, ev.release_time) - 0.5
        ref = None
        for t, gray, people in reversed(self.snaps):
            if t > cutoff:
                continue
            if not any(boxes_overlap(expand(p, 0.1), region) for p in people):
                ref = gray
                break
        if ref is None:
            return None
        s = self.scale
        x1, y1 = max(0, int(region[0] * s)), max(0, int(region[1] * s))
        x2, y2 = min(ref.shape[1], int(region[2] * s)), min(ref.shape[0], int(region[3] * s))
        if x2 - x1 < 4 or y2 - y1 < 4:
            return None
        now = self._gray(frame)
        diff = float(np.mean(cv2.absdiff(ref[y1:y2, x1:x2], now[y1:y2, x1:x2])))
        log.debug("Background check for %s: diff=%.1f", ev.event_id, diff)
        return diff < max_diff


# -------------------------------------------------------------- pipeline

@dataclass
class RunSummary:
    run_id: str
    source: str
    frames: int = 0
    seconds: float = 0.0
    fps_processed: float = 0.0
    events: list[dict] = field(default_factory=list)
    suppressed: list[dict] = field(default_factory=list)
    output_dir: str = ""


def _open_source(source: str):
    src = int(source) if str(source).isdigit() else source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")
    live = isinstance(src, int) or str(source).startswith(("rtsp://", "http://", "https://"))
    return cap, live


def draw_live(frame, dets: list[Detection], flash: str | None):
    for d in dets:
        color = (200, 200, 200) if d.kind == "person" else (80, 200, 255)
        x1, y1, x2, y2 = (int(v) for v in d.box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d.cls_name} #{d.track_id} {d.conf:.2f}"
        cv2.putText(frame, label, (x1, max(12, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    if flash:
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (40, 40, 230), -1)
        cv2.putText(frame, flash, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


class Pipeline:
    def __init__(self, cfg: Config, api: ApiClient | None = None, job_id: str | None = None,
                 tracker=None):
        self.cfg = cfg
        self.api = api
        self.job_id = job_id
        self.tracker = tracker or Tracker(cfg)

    def _job(self, **fields):
        if self.api and self.job_id:
            self.api.update_job(self.job_id, **fields)

    def run(self, source: str, show: bool = False, video_name: str | None = None,
            max_seconds: float | None = None) -> RunSummary:
        cfg = self.cfg
        cap, live = _open_source(source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if fps <= 1 or fps > 240:
            fps = 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        out_dir = Path(cfg.evidence.output_dir) / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        annotated_path = out_dir / "annotated.mp4"
        annotated_writer = None
        if not live and w > 0 and h > 0:
            codec = cv2.VideoWriter_fourcc(*"mp4v")
            annotated_writer = cv2.VideoWriter(
                str(annotated_path), codec, fps, (w, h)
            )
            if not annotated_writer.isOpened():
                annotated_writer.release()
                annotated_writer = None
                log.warning("Could not create annotated video at %s", annotated_path)

        summary = RunSummary(run_id=run_id, source=str(source), output_dir=str(out_dir))
        log.info("Run %s: %s (%dx%d @ %.1f fps, %s frames)", run_id, source, w, h, fps, total or "live")

        events = LitterEventDetector(cfg.events, w, h, cfg.camera.bin_zones, cfg.camera.ignore_zones)
        recorder = EvidenceRecorder(cfg.evidence, fps, w, h, out_dir)
        history = SceneHistory(w, h)
        started_at = datetime.now(timezone.utc)
        wall_start = time.monotonic()
        self._job(status="running", progress=0.0, run_id=run_id)

        stride = max(1, cfg.model.vid_stride)
        idx = 0
        dets: list[Detection] = []
        flash_until, flash_text = -1.0, None
        last_progress = -1.0

        def handle(files: list[EvidenceFiles]):
            for ef in files:
                summary.events.append({**ef.meta, "folder": str(ef.folder)})
                if self.api:
                    self.api.post_violation(ef.meta, ef.clip, ef.contact, ef.scene)

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                t = (time.monotonic() - wall_start) if live else idx / fps
                if max_seconds is not None and t > max_seconds:
                    break

                if idx % stride == 0:
                    dets = self.tracker(frame)
                    history.add(t, frame, dets)
                    handle(recorder.push(idx, t, frame, dets))

                    for ev in events.update(t, idx, dets):
                        if cfg.events.verify_new_object:
                            old = history.was_already_there(ev, frame, cfg.events.verify_diff)
                            log.info(
                                "Verification details: event=%s contact=%.2fs release=%.2fs "
                                "detected=%.2fs old=%s threshold=%.1f",
                                ev.event_id,
                                ev.contact_time,
                                ev.release_time,
                                ev.detected_time,
                                old,
                                cfg.events.verify_diff,
                            )
                            if old:
                                summary.suppressed.append({"reason": "already_there", "event_id": ev.event_id})
                                log.info("Suppressed %s: litter was already there", ev.event_id)
                                continue
                            ev.verified_new = None if old is None else True
                        meta = {
                            "run_id": run_id,
                            "camera_id": cfg.camera.id,
                            "location": cfg.camera.location,
                            "video_name": video_name or Path(str(source)).name,
                            "job_id": self.job_id,
                            "fps": fps,
                            "detected_at": (started_at.timestamp() + ev.detected_time),
                            "live": live,
                        }
                        recorder.start(ev, t, meta)
                        log.info("Littering: %s by person #%s at t=%.1fs (conf %.2f)",
                                 ev.waste_type, ev.person_track_id, t, ev.confidence)
                        flash_until, flash_text = t + 2, f"Littering detected: {ev.waste_type}"
                else:
                    handle(recorder.push(idx, t, frame, dets))

                if annotated_writer is not None:
                    annotated = draw_live(
                        frame.copy(), dets,
                        flash_text if t < flash_until else None
                    )
                    annotated_writer.write(annotated)

                if show:
                    view = draw_live(frame.copy(), dets, flash_text if t < flash_until else None)
                    cv2.imshow("CleanVision (press q to stop)", view)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                if total and self.job_id:
                    progress = round(idx / total, 2)
                    if progress - last_progress >= 0.05:
                        self._job(progress=progress, events=len(summary.events))
                        last_progress = progress
                idx += 1
        except Exception as exc:
            self._job(status="failed", error=str(exc))
            raise
        finally:
            cap.release()
            if annotated_writer is not None:
                annotated_writer.release()
                log.info("Annotated video saved: %s", annotated_path)
            if show:
                cv2.destroyAllWindows()
            handle(recorder.flush())

        elapsed = time.monotonic() - wall_start
        summary.frames = idx
        summary.seconds = round(idx / fps, 2)
        summary.fps_processed = round(idx / elapsed, 1) if elapsed > 0 else 0.0
        summary.suppressed += [{"reason": r, "object_track_id": o} for r, o in events.suppressed]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(summary.__dict__, indent=2, default=str), encoding="utf-8")
        self._job(status="completed", progress=1.0, events=len(summary.events))
        log.info("Done: %d frames, %d events, %.1f fps", idx, len(summary.events), summary.fps_processed)
        return summary
