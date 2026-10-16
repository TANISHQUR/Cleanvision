"""Checks COCO/YOLO conversion, EXIF handling, class mapping and clip-grouped splits."""
import json

import yaml
from PIL import Image

from dataset import prepare_dataset as prep


def make_exif_rotated(path, w, h):
    """Save a w x h (portrait) image the way phones do: landscape pixels + EXIF 'rotate 90'."""
    img = Image.new("RGB", (h, w), "white")
    exif = img.getexif()
    exif[0x0112] = 6
    img.save(path, exif=exif)


def test_prepare_dataset(tmp_path):
    coco_dir = tmp_path / "taco"
    coco_dir.mkdir()
    make_exif_rotated(coco_dir / "a.jpg", 300, 400)          # labels drawn on 300x400 portrait
    Image.new("RGB", (400, 300), "gray").save(coco_dir / "b.jpg")
    Image.new("RGB", (400, 300), "gray").save(coco_dir / "c.jpg")   # background only
    coco = {
        "images": [
            {"id": 1, "file_name": "a.jpg", "width": 300, "height": 400},
            {"id": 2, "file_name": "b.jpg", "width": 400, "height": 300},
            {"id": 3, "file_name": "c.jpg", "width": 400, "height": 300},
            {"id": 4, "file_name": "missing.jpg", "width": 10, "height": 10},
        ],
        "categories": [{"id": 5, "name": "Clear plastic bottle"}, {"id": 12, "name": "Drink can"},
                       {"id": 59, "name": "Cigarette"}],
        "annotations": [
            {"image_id": 1, "category_id": 5, "bbox": [30, 40, 60, 80]},
            {"image_id": 2, "category_id": 12, "bbox": [0, 0, 40, 30]},
            {"image_id": 2, "category_id": 59, "bbox": [100, 100, 10, 10]},
            {"image_id": 3, "category_id": 59, "bbox": [100, 100, 10, 10]},
        ],
    }
    (coco_dir / "ann.json").write_text(json.dumps(coco))

    own = tmp_path / "own"
    own.mkdir()
    for clip in ("walk1", "walk2"):
        for f in (0, 15, 30):
            Image.new("RGB", (64, 48)).save(own / f"{clip}_f{f:06d}.jpg")
            (own / f"{clip}_f{f:06d}.txt").write_text("1 0.1 0.1 0.2 0.1 0.3 0.3\n0 0.5 0.5 0.2 0.2\n")
    (own / "data.yaml").write_text(yaml.safe_dump({"names": ["person", "wrapper"]}))

    cfg = {
        "output": str(tmp_path / "out"),
        "classes": ["person", "bottle", "can", "wrapper", "paper"],
        "val_ratio": 0.5, "seed": 1, "background_ratio": 1.0,
        "auto_label_persons": {"enabled": False},
        "sources": [
            {"name": "taco", "type": "coco", "images_dir": str(coco_dir),
             "annotations": str(coco_dir / "ann.json"),
             "map": {"bottle": ["Clear plastic bottle"], "can": ["Drink can"]}},
            {"name": "own", "type": "yolo", "images_dir": str(own), "names_from": str(own / "data.yaml"),
             "map": {"person": ["person"], "wrapper": ["wrapper"]}, "has_person_labels": True,
             "group_by_clip": True, "val_ratio": 0.5},
        ],
    }
    cfg_path = tmp_path / "sources.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    prep.main(["--config", str(cfg_path)])

    out = tmp_path / "out"
    labels = {p.stem: p.read_text() for p in out.rglob("labels/*/*.txt")}
    assert len(labels) == 3 + 6

    # EXIF image saved upright with the label unchanged
    a_img = next(out.rglob("images/*/taco__a.jpg"))
    assert Image.open(a_img).size == (300, 400)
    cls, xc, yc, w, h = labels["taco__a"].split()
    assert cls == "1" and abs(float(xc) - 0.2) < 1e-4 and abs(float(h) - 0.2) < 1e-4

    # Cigarette dropped, can kept as class 2
    assert labels["taco__b"].strip().splitlines() == ["2 0.050000 0.050000 0.100000 0.100000"]
    assert labels["taco__c"] == ""

    # polygon converted to a box; person kept as class 0
    first = labels["own__walk1_f000000"].splitlines()
    assert first[0] == "3 0.200000 0.200000 0.200000 0.200000"
    assert first[1].startswith("0 ")

    # all frames of a clip in the same split
    for clip in ("walk1", "walk2"):
        splits = {p.parent.name for p in out.rglob(f"images/*/own__{clip}_*.jpg")}
        assert len(splits) == 1

    data = yaml.safe_load((out / "cleanvision.yaml").read_text())
    assert data["names"][3] == "wrapper"
    report = json.loads((out / "report.json").read_text())
    assert sum(report["images"].values()) == 9
