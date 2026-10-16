"""
Measure how well the littering rule works on your own labelled test clips.
This gives you precision / recall numbers for the project report.

1. Put test videos in one folder (include clips with NO littering too).
2. Write a CSV listing each littering act you performed:

       video,start_s,end_s
       clip01.mp4,4.0,7.5
       clip03.mp4,2.0,5.0
       clip03.mp4,12.0,15.0

   start_s/end_s bracket the moment the object leaves the hand and lands.
   Videos not in the CSV are treated as "no littering".

3. Run:
       python tools/evaluate_events.py --videos test_clips --labels test_clips/labels.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import defaultdict
from pathlib import Path

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}


def match(preds: list[float], truths: list[tuple[float, float]], tol: float):
    used = set()
    tp = 0
    for p in sorted(preds):
        for k, (s, e) in enumerate(truths):
            if k not in used and s - tol <= p <= e + tol:
                used.add(k)
                tp += 1
                break
    return tp, len(preds) - tp, len(truths) - len(used)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--weights")
    ap.add_argument("--tolerance", type=float, default=2.0, help="seconds of slack around each labelled act")
    ap.add_argument("--out", default="storage/eval_results.json")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from detector.config import load_config
    from detector.pipeline import Pipeline, Tracker

    truths = defaultdict(list)
    with open(args.labels, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            truths[row["video"].strip()].append((float(row["start_s"]), float(row["end_s"])))

    cfg = load_config(args.config)
    if args.weights:
        cfg.model.weights = args.weights
    cfg.evidence.output_dir = "storage/eval_runs"

    videos = sorted(p for p in Path(args.videos).iterdir() if p.suffix.lower() in VIDEO_EXT)
    rows, TP, FP, FN = [], 0, 0, 0
    for v in videos:
        tracker = Tracker(cfg)          # fresh tracker so IDs don't carry over between clips
        summary = Pipeline(cfg, tracker=tracker).run(str(v))
        preds = [e["release_time"] for e in summary.events]
        tp, fp, fn = match(preds, truths.get(v.name, []), args.tolerance)
        TP, FP, FN = TP + tp, FP + fp, FN + fn
        rows.append({"video": v.name, "labelled": len(truths.get(v.name, [])), "detected": len(preds),
                     "tp": tp, "fp": fp, "fn": fn, "fps": summary.fps_processed})
        print(f"{v.name:<30} labelled={rows[-1]['labelled']} detected={len(preds)} tp={tp} fp={fp} fn={fn}")

    precision = TP / (TP + FP) if TP + FP else 0.0
    recall = TP / (TP + FN) if TP + FN else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    result = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
              "tp": TP, "fp": FP, "fn": FN, "tolerance_s": args.tolerance, "videos": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(f"\nPrecision {precision:.2f}  Recall {recall:.2f}  F1 {f1:.2f}   (saved to {args.out})")


if __name__ == "__main__":
    main()
