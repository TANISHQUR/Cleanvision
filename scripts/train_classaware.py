from pathlib import Path
import shutil
import yaml
import torch

from ultralytics import YOLO
from ultralytics.models.yolo.detect import DetectionTrainer
from ultralytics.nn.tasks import DetectionModel
from ultralytics.utils.loss import v8DetectionLoss
from ultralytics.utils.tal import make_anchors


ROOT = Path.cwd()
STAGING = ROOT / "datasets/cleanvision_expanded"
DATASET = ROOT / "datasets/cleanvision_classaware"

BASE_MODEL = (
    ROOT / "runs/detect/runs/detect/"
    "cv_bottle_finetune_01/weights/best.pt"
)

CLASS_NAMES = {
    0: "person",
    1: "bottle",
    2: "can",
    3: "wrapper",
    4: "paper",
}

# Original images have annotations for all five classes.
# Waste images have annotations for bottle, can, and wrapper only.
ALL_CLASSES = [1, 1, 1, 1, 1]
WASTE_CLASSES = [0, 1, 1, 1, 0]


def prepare_dataset():
    if not BASE_MODEL.exists():
        raise FileNotFoundError(
            f"Starting checkpoint not found: {BASE_MODEL}"
        )

    # Rebuild only this dedicated symlink dataset.
    # The source images, labels, and existing model remain untouched.
    if DATASET.exists():
        shutil.rmtree(DATASET)

    for split in ("train", "val"):
        (DATASET / "images" / split).mkdir(parents=True)
        (DATASET / "labels" / split).mkdir(parents=True)

    def link_split(source_name, destination_split, prefix):
        source_images = STAGING / "images" / source_name
        source_labels = STAGING / "labels" / source_name

        if not source_images.is_dir() or not source_labels.is_dir():
            raise FileNotFoundError(
                f"Missing source split: {source_images} or {source_labels}"
            )

        count = 0
        for image_path in sorted(source_images.iterdir()):
            if not image_path.is_file():
                continue
            if image_path.suffix.lower() not in {
                ".jpg", ".jpeg", ".png", ".bmp", ".webp"
            }:
                continue

            label_path = source_labels / f"{image_path.stem}.txt"
            if not label_path.exists():
                raise FileNotFoundError(
                    f"Missing label for {image_path}"
                )

            new_name = f"{prefix}{image_path.name}"
            new_image = DATASET / "images" / destination_split / new_name
            new_label = (
                DATASET / "labels" / destination_split
                / f"{Path(new_name).stem}.txt"
            )

            new_image.symlink_to(image_path.resolve())
            new_label.symlink_to(label_path.resolve())
            count += 1

        return count

    original_train = link_split("train", "train", "orig__")
    waste_train = link_split("waste_train", "train", "waste__")
    original_val = link_split("val", "val", "orig__")

    if not original_train or not waste_train or not original_val:
        raise RuntimeError("One or more dataset splits are empty.")

    config = {
        "path": str(DATASET),
        "train": "images/train",
        "val": "images/val",
        "names": CLASS_NAMES,
    }

    yaml_path = DATASET / "data.yaml"
    with yaml_path.open("w") as f:
        yaml.safe_dump(config, f, sort_keys=False)

    print("\nDataset prepared")
    print(f"Original training images: {original_train}")
    print(f"Waste training images:    {waste_train}")
    print(f"Original validation:      {original_val}")
    print(f"Dataset YAML:             {yaml_path}")

    return yaml_path


class ClassAwareDetectionLoss(v8DetectionLoss):
    """Mask classification loss for classes absent from a source's labels."""

    def get_assigned_targets_and_loss(self, preds, batch):
        loss = torch.zeros(3, device=self.device)

        pred_distri, pred_scores = (
            preds["boxes"].permute(0, 2, 1).contiguous(),
            preds["scores"].permute(0, 2, 1).contiguous(),
        )

        anchor_points, stride_tensor = make_anchors(
            preds["feats"], self.stride, 0.5
        )

        dtype = pred_scores.dtype
        batch_size = pred_scores.shape[0]

        imgsz = (
            torch.tensor(
                preds["feats"][0].shape[2:],
                device=self.device,
                dtype=dtype,
            )
            * self.stride[0]
        )

        targets = torch.cat(
            (
                batch["batch_idx"].view(-1, 1),
                batch["cls"].view(-1, 1),
                batch["bboxes"],
            ),
            1,
        )

        targets = self.preprocess(
            targets.to(self.device),
            batch_size,
            scale_tensor=imgsz[[1, 0, 1, 0]],
        )

        gt_labels, gt_bboxes = targets.split((1, 4), 2)
        mask_gt = gt_bboxes.sum(2, keepdim=True).gt_(0.0)

        pred_bboxes = self.bbox_decode(anchor_points, pred_distri)

        _, target_bboxes, target_scores, fg_mask, target_gt_idx = (
            self.assigner(
                pred_scores.detach().sigmoid(),
                (
                    pred_bboxes.detach() * stride_tensor
                ).type(gt_bboxes.dtype),
                anchor_points * stride_tensor,
                gt_labels,
                gt_bboxes,
                mask_gt,
            )
        )

        target_scores_sum = target_scores.sum().clamp_(min=1)

        bce_loss = self.bce(
            pred_scores, target_scores.to(dtype)
        )

        # [batch, 1, classes] broadcasts across every prediction anchor.
        # Unknown classes contribute no classification penalty.
        coverage = batch.get("class_coverage")

        # Validation uses the fully annotated original dataset.
        # If no mask is supplied, evaluate all five classes.
        if coverage is None:
            coverage = torch.ones(
                (pred_scores.shape[0], pred_scores.shape[2]),
                device=pred_scores.device,
                dtype=bce_loss.dtype,
            )
        else:
            coverage = coverage.to(
                device=pred_scores.device, dtype=bce_loss.dtype
            )

        bce_loss = bce_loss * coverage[:, None, :]

        if self.class_weights is not None:
            bce_loss *= self.class_weights

        loss[1] = bce_loss.sum() / target_scores_sum

        loss[0], loss[2] = self.bbox_loss(
            pred_distri,
            pred_bboxes,
            anchor_points,
            target_bboxes / stride_tensor,
            target_scores,
            target_scores_sum,
            fg_mask,
            imgsz,
            stride_tensor,
        )

        loss[0] *= self.hyp.box
        loss[1] *= self.hyp.cls
        loss[2] *= self.hyp.dfl

        return (
            (
                fg_mask,
                target_gt_idx,
                target_bboxes,
                anchor_points,
                stride_tensor,
            ),
            loss,
            dict(zip(self.loss_names, loss.detach())),
        )



class ClassAwareDetectionModel(DetectionModel):
    def init_criterion(self):
        # DetectionTrainer normally attaches these hyperparameters.
        # Supply defaults for standalone checks if they are not present.
        if not hasattr(self, "args"):
            from ultralytics.cfg import get_cfg
            self.args = get_cfg()
        return ClassAwareDetectionLoss(self)


class ClassAwareTrainer(DetectionTrainer):
    def get_model(self, cfg=None, weights=None, verbose=True):
        model = ClassAwareDetectionModel(
            cfg or "yolo11n.yaml",
            nc=self.data["nc"],
            verbose=verbose,
        )
        if weights:
            model.load(weights)
        return model

    def preprocess_batch(self, batch):
        batch = super().preprocess_batch(batch)
        image_paths = batch.get("im_file")
        if image_paths is None:
            raise RuntimeError("Image paths missing for class-aware masking.")

        masks = []
        for image_path in image_paths:
            is_waste = Path(image_path).name.startswith("waste__")
            masks.append(WASTE_CLASSES if is_waste else ALL_CLASSES)

        batch["class_coverage"] = torch.tensor(
            masks, dtype=torch.float32, device=self.device
        )
        return batch


def main():
    yaml_path = prepare_dataset()

    print("\nStarting checkpoint:", BASE_MODEL)
    print("Training device: MPS when supported by Ultralytics")
    print("Classes:", CLASS_NAMES)
    print("Masked waste classes: person, paper")

    trainer = ClassAwareTrainer(
        overrides={
            "model": str(BASE_MODEL),
            "data": str(yaml_path),
            "epochs": 50,
            "patience": 10,
            "batch": 8,
            "imgsz": 640,
            "workers": 4,
            "device": "mps",
            "project": str(ROOT / "runs/detect"),
            "name": "cleanvision_classaware_v1",
            "exist_ok": True,
            "pretrained": True,
            "optimizer": "auto",
            "seed": 42,
            "plots": True,
            "save": True,
            "val": True,
        }
    )

    trainer.train()


if __name__ == "__main__":
    main()
