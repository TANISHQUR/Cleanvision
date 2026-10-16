#!/usr/bin/env bash
set -euo pipefail

MODEL_URL="https://github.com/TANISHQUR/Cleanvision/releases/download/v1.0.0-models/cleanvision-models.zip"
MODEL_DIR="runs/detect/cleanvision_classaware_v1/weights"

mkdir -p "$MODEL_DIR"
curl -fL --retry 3 "$MODEL_URL" -o /tmp/cleanvision-models.zip

mkdir -p /tmp/cleanvision-models
unzip -o /tmp/cleanvision-models.zip -d /tmp/cleanvision-models

cp /tmp/cleanvision-models/best.pt "$MODEL_DIR/best.pt"
cp /tmp/cleanvision-models/yolo11n.pt ./yolo11n.pt

test -s "$MODEL_DIR/best.pt"
test -s ./yolo11n.pt

echo "CleanVision model weights installed successfully."
