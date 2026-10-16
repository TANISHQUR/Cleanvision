"""
Draw dustbin / ignore zones on a frame from your camera and get the numbers for config.yaml.

    python tools/pick_zones.py --source demo.mp4 --at 2.0

Drag a rectangle, press ENTER or SPACE to confirm it, repeat, then press ESC when done.
"""
from __future__ import annotations

import argparse

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--at", type=float, default=0.0, help="second of the video to show")
    args = ap.parse_args()

    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    if args.at:
        cap.set(cv2.CAP_PROP_POS_MSEC, args.at * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("Could not read a frame from the source")
    h, w = frame.shape[:2]
    rois = cv2.selectROIs("Draw zones (ENTER to add, ESC to finish)", frame, showCrosshair=False)
    cv2.destroyAllWindows()
    zones = [[round(x / w, 3), round(y / h, 3), round((x + rw) / w, 3), round((y + rh) / h, 3)]
             for x, y, rw, rh in rois]
    print("\nPaste under camera: in config.yaml, e.g.")
    print(f"  bin_zones: {zones}")


if __name__ == "__main__":
    main()
