"""Load config.yaml into plain dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    weights: str = "yolo11n.pt"
    imgsz: int = 960
    conf: float = 0.15
    iou: float = 0.5
    device: Any = 0
    half: bool = True
    tracker: str = "bytetrack.yaml"
    vid_stride: int = 1
    person_class: str = "person"
    litter_classes: list[str] = field(default_factory=lambda: ["bottle", "can", "wrapper", "paper", "cup"])
    person_weights: str | None = None


@dataclass
class EventConfig:
    near_margin: float = 0.25
    assoc_window_s: float = 1.0
    min_contact_s: float = 0.3
    stationary_window_s: float = 1.0
    stationary_tol: float = 0.02
    linger_s: float = 2.0
    separation: float = 0.8
    absent_s: float = 0.7
    min_object_conf: float = 0.35
    track_timeout_s: float = 3.0
    dedupe_iou: float = 0.3
    dedupe_s: float = 60.0
    verify_new_object: bool = True
    verify_diff: float = 18.0


@dataclass
class EvidenceConfig:
    output_dir: str = "storage/local_runs"
    pre_s: float = 8.0
    post_s: float = 2.0
    fps: float = 15.0
    max_width: int = 960
    jpeg_quality: int = 85


@dataclass
class CameraConfig:
    id: str = "CAM-01"
    location: str = "Unknown"
    bin_zones: list[list[float]] = field(default_factory=list)
    ignore_zones: list[list[float]] = field(default_factory=list)


@dataclass
class ApiConfig:
    url: str | None = "http://127.0.0.1:8000"
    token: str = "change-me-detector-token"


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    events: EventConfig = field(default_factory=EventConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


def _build(cls, data: dict | None):
    data = data or {}
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown keys in '{cls.__name__}' section of config: {sorted(unknown)}")
    return cls(**data)


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw = raw or {}
    return Config(
        model=_build(ModelConfig, raw.get("model")),
        events=_build(EventConfig, raw.get("events")),
        evidence=_build(EvidenceConfig, raw.get("evidence")),
        camera=_build(CameraConfig, raw.get("camera")),
        api=_build(ApiConfig, raw.get("api")),
    )
