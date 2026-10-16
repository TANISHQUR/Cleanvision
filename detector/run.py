"""
Run the detector on a video file, webcam or stream.

Examples
  python -m detector.run --source samples/demo.mp4 --show
  python -m detector.run --source 0 --show                 # webcam
  python -m detector.run --source clip.mp4 --no-api        # save evidence locally only
"""
from __future__ import annotations

import argparse
import logging
import os

from .api_client import ApiClient
from .config import load_config
from .pipeline import Pipeline
from . import checkpoint_compat  # register custom checkpoint class before YOLO loads weights


def main(argv=None):
    ap = argparse.ArgumentParser(description="CleanVision littering detector")
    ap.add_argument("--source", required=True, help="video path, webcam index (0) or rtsp:// URL")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--weights", help="override model.weights")
    ap.add_argument("--device", help="override model.device, e.g. 0 or cpu")
    ap.add_argument("--camera-id")
    ap.add_argument("--location")
    ap.add_argument("--api-url", help="override api.url")
    ap.add_argument("--no-api", action="store_true", help="don't send anything to the backend")
    ap.add_argument("--job-id", help="set by the backend when it launches the detector")
    ap.add_argument("--video-name", help="original file name, used by the backend")
    ap.add_argument("--show", action="store_true", help="open a live preview window")
    ap.add_argument("--max-seconds", type=float)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    if args.weights:
        cfg.model.weights = args.weights
    if args.device:
        cfg.model.device = int(args.device) if args.device.isdigit() else args.device
    if args.camera_id:
        cfg.camera.id = args.camera_id
    if args.location:
        cfg.camera.location = args.location
    if args.api_url:
        cfg.api.url = args.api_url

    # The backend passes its token this way when it launches the detector.
    cfg.api.token = os.environ.get("CLEANVISION_API_TOKEN", cfg.api.token)
    api = None if args.no_api or not cfg.api.url else ApiClient(cfg.api.url, cfg.api.token)
    pipeline = Pipeline(cfg, api=api, job_id=args.job_id)
    summary = pipeline.run(args.source, show=args.show, video_name=args.video_name,
                           max_seconds=args.max_seconds)
    print(f"\n{len(summary.events)} littering event(s). Evidence saved in {summary.output_dir}")


if __name__ == "__main__":
    main()
