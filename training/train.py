"""
Train the litter detector. Settings are tuned for a 4 GB laptop GPU (RTX 3050).

    python training/train.py --data datasets/cleanvision/cleanvision.yaml
    python training/train.py --data ... --model yolo11s.pt --imgsz 800     # bigger model, smaller images

Weights end up in runs/detect/<name>/weights/best.pt
"""
from __future__ import annotations

import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="datasets/cleanvision/cleanvision.yaml")
    ap.add_argument("--model", default="yolo11n.pt", help="starting weights (COCO-pretrained)")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=960, help="960 helps with small litter; drop to 800 on OOM")
    ap.add_argument("--batch", type=float, default=-1, help="-1 = auto-fit to GPU memory")
    ap.add_argument("--device", default="0")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cache", default="disk", help='"disk", "ram" or "none"')
    ap.add_argument("--name", default="cleanvision")
    ap.add_argument("--resume", action="store_true", help="continue an interrupted run")
    args = ap.parse_args()

    from ultralytics import YOLO

    if args.resume:
        YOLO(f"runs/detect/{args.name}/weights/last.pt").train(resume=True)
        return

    model = YOLO(args.model)
    batch = int(args.batch) if args.batch >= 1 or args.batch == -1 else args.batch
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=batch,
        device=args.device,
        workers=args.workers,
        amp=True,               # mixed precision, roughly halves memory use
        cache=False if args.cache == "none" else args.cache,           # RAM caching fills 16 GB quickly
        patience=20,            # stop early when validation stops improving
        cos_lr=True,
        close_mosaic=10,
        # Litter is often upside down or on its side, so allow flips.
        flipud=0.5,
        fliplr=0.5,
        degrees=45,
        project="runs/detect",
        name=args.name,
        exist_ok=True,
        plots=True,
        scale = 0.6
    )
    metrics = model.val(data=args.data, imgsz=args.imgsz, device=args.device)
    print("\nPer-class mAP50-95:")
    for i, c in enumerate(metrics.box.ap_class_index):
        print(f"  {model.names[int(c)]:<10} {metrics.box.maps[int(c)]:.3f}")
    print(f"\nBest weights: runs/detect/{args.name}/weights/best.pt")
    print("Set model.weights in config.yaml to that path.")


if __name__ == "__main__":
    # Needed on Windows: dataloader workers re-import this file.
    main()
