"""
Evidence recording.

Keeps the last few seconds of video in memory (as JPEG bytes, so a few MB),
and when an event fires, writes:

  clip.mp4     short H.264 video around the event, with boxes drawn
  contact.jpg  the frame where the person was last seen with the object
  scene.jpg    the frame where the event fired (object on the ground)
  event.json   metadata
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .config import EvidenceConfig
from .events import Detection, LitterEvent

log = logging.getLogger(__name__)

PERSON_COLOR = (200, 200, 200)
LITTER_COLOR = (80, 200, 255)
SUSPECT_COLOR = (0, 170, 255)     # amber (BGR)
OBJECT_COLOR = (40, 40, 230)      # red (BGR)


@dataclass
class _Frame:
    index: int
    t: float
    jpeg: bytes
    dets: list[Detection]


@dataclass
class _Pending:
    event: LitterEvent
    frames: list[_Frame]
    end_t: float
    meta: dict = field(default_factory=dict)


@dataclass
class EvidenceFiles:
    event: LitterEvent
    folder: Path
    clip: Path | None
    contact: Path
    scene: Path
    meta: dict


def _even(v: int) -> int:
    return v - (v % 2)


class EvidenceRecorder:
    def __init__(self, cfg: EvidenceConfig, src_fps: float, frame_w: int, frame_h: int, out_dir: Path):
        self.cfg = cfg
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.step = max(1, round(src_fps / max(cfg.fps, 1)))
        self.clip_fps = src_fps / self.step
        self.scale = min(1.0, cfg.max_width / frame_w)
        self.out_w = _even(int(frame_w * self.scale))
        self.out_h = _even(int(frame_h * self.scale))
        self.buffer: deque[_Frame] = deque(maxlen=int(cfg.pre_s * self.clip_fps) + 2)
        self.pending: list[_Pending] = []

    # ------------------------------------------------------------ capture
    def push(self, index: int, t: float, frame: np.ndarray, dets: list[Detection]) -> list[EvidenceFiles]:
        if index % self.step == 0:
            small = cv2.resize(frame, (self.out_w, self.out_h), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.cfg.jpeg_quality])
            if ok:
                f = _Frame(index, t, buf.tobytes(), list(dets))
                self.buffer.append(f)
                for p in self.pending:
                    p.frames.append(f)
        done = [p for p in self.pending if t >= p.end_t]
        self.pending = [p for p in self.pending if t < p.end_t]
        return [self._write(p) for p in done]

    def start(self, event: LitterEvent, t: float, meta: dict) -> None:
        self.pending.append(_Pending(event, list(self.buffer), t + self.cfg.post_s, meta))

    def flush(self) -> list[EvidenceFiles]:
        done, self.pending = self.pending, []
        return [self._write(p) for p in done]

    # ------------------------------------------------------------- output
    def _render(self, f: _Frame, ev: LitterEvent) -> np.ndarray:
        img = cv2.imdecode(np.frombuffer(f.jpeg, np.uint8), cv2.IMREAD_COLOR)
        s = self.scale
        for d in f.dets:
            x1, y1, x2, y2 = (int(v * s) for v in d.box)
            if d.kind == "person" and d.track_id == ev.person_track_id:
                color, thick, label = SUSPECT_COLOR, 3, f"Person #{d.track_id}"
            elif d.kind == "litter" and d.track_id == ev.object_track_id:
                color, thick, label = OBJECT_COLOR, 3, d.cls_name
            else:
                color = PERSON_COLOR if d.kind == "person" else LITTER_COLOR
                thick, label = 1, None
            cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
            if label:
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(img, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, y1), color, -1)
                cv2.putText(img, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)
        stamp = f"t={f.t:6.2f}s  frame {f.index}"
        cv2.putText(img, stamp, (10, self.out_h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, stamp, (10, self.out_h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        return img

    @staticmethod
    def _nearest(frames: list[_Frame], index: int) -> _Frame:
        return min(frames, key=lambda f: abs(f.index - index))

    def _write_video(self, path: Path, images: list[np.ndarray]) -> Path | None:
        try:
            import imageio_ffmpeg

            writer = imageio_ffmpeg.write_frames(
                str(path), (self.out_w, self.out_h), fps=self.clip_fps,
                codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
                output_params=["-movflags", "+faststart"], macro_block_size=2,
            )
            writer.send(None)
            for img in images:
                writer.send(np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            writer.close()
            return path
        except Exception as exc:  # fall back to OpenCV (plays in VLC, maybe not in browsers)
            log.warning("imageio-ffmpeg failed (%s), falling back to OpenCV mp4v", exc)
            vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), self.clip_fps, (self.out_w, self.out_h))
            if not vw.isOpened():
                return None
            for img in images:
                vw.write(img)
            vw.release()
            return path

    def _write(self, p: _Pending) -> EvidenceFiles:
        ev = p.event
        folder = self.out_dir / ev.event_id
        folder.mkdir(parents=True, exist_ok=True)
        frames = p.frames or list(self.buffer)

        contact_img = self._render(self._nearest(frames, ev.contact_frame_index), ev)
        scene_img = self._render(self._nearest(frames, ev.frame_index), ev)
        contact_path, scene_path = folder / "contact.jpg", folder / "scene.jpg"
        cv2.imwrite(str(contact_path), contact_img)
        cv2.imwrite(str(scene_path), scene_img)

        clip = self._write_video(folder / "clip.mp4", [self._render(f, ev) for f in frames])
        meta = {**p.meta, **ev.to_dict(),
                "clip_start_time": round(frames[0].t, 2), "clip_end_time": round(frames[-1].t, 2)}
        (folder / "event.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return EvidenceFiles(ev, folder, clip, contact_path, scene_path, meta)
