"""Quick check that PyTorch sees your GPU and YOLO runs on it."""
import time

import torch

print("PyTorch", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("PyTorch can't see the GPU. Reinstall the CUDA build from https://pytorch.org")
print("GPU:", torch.cuda.get_device_name(0))
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

import numpy as np
from ultralytics import YOLO

model = YOLO("yolo11n.pt")
frame = np.zeros((720, 1280, 3), np.uint8)
model.predict(frame, imgsz=960, device=0, verbose=False)
start = time.time()
for _ in range(30):
    model.predict(frame, imgsz=960, device=0, verbose=False)
print(f"YOLO11n at 960px: {30 / (time.time() - start):.0f} frames per second")
