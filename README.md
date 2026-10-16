# CleanVision: AI-based littering detection

CleanVision watches video for people dropping litter. It detects people and litter with YOLO, tracks them with ByteTrack, and decides whether someone actually littered by looking at how the person and the object behave over time. Every incident is saved with a short clip and two still frames, then sent to a web portal where an admin reviews it, links it to a person in a simulated citizen registry, and issues a challan.

```
 camera / video file
        │
        ▼
 detector/  ──  YOLO11 + ByteTrack  ──  littering rule  ──  evidence (clip + stills)
        │                                                        │
        └──────────────── HTTP upload ───────────────────────────┘
                                   ▼
 backend/   FastAPI + MongoDB   (violations, citizens, challans, video jobs)
                                   ▼
 frontend/  React portal        (review queue, decisions, challans, uploads)
```

## Project layout

| Folder | What's inside |
|---|---|
| `detector/` | `events.py` has the littering rule. `pipeline.py` has the video loop, YOLO tracking and the background check. `evidence.py` writes clips and stills. `run.py` is the command-line entry point. |
| `backend/app/` | FastAPI app. `routers/` holds the endpoints, `jobs_runner.py` runs the detector on uploaded videos, `seed.py` holds the fake citizen registry. |
| `frontend/` | React (Vite) admin portal. |
| `dataset/` | `prepare_dataset.py` merges datasets into YOLO format. `extract_frames.py` pulls frames from your own clips for labelling. `sources.yaml` holds the class mapping. |
| `training/train.py` | Training settings for a 4 GB GPU. |
| `tools/` | `evaluate_events.py` computes precision and recall on test clips. `pick_zones.py` lets you draw dustbin zones. |
| `tests/` | 18 automated tests. Run `pytest`. |
| `config.yaml` | Every detector setting in one place. |
| `docs/how-detection-works.md` | Plain explanation of the rule, for the report and viva. |

## Setup on Windows

You need Python 3.10 to 3.12, Node.js 18 or newer, and Git. MongoDB is optional (see step 4).

**1. Python environment**

```bat
cd cleanvision
python -m venv .venv
.venv\Scripts\activate
```

**2. PyTorch with CUDA.** Go to https://pytorch.org, pick Stable, Windows, Pip, Python, and the CUDA version your driver supports (run `nvidia-smi` to see it). Run the command it gives you. Then:

```bat
pip install -r requirements.txt
python scripts\check_gpu.py
```

`check_gpu.py` should print your RTX 3050 and a frames-per-second number. If it says CUDA is not available, you installed the CPU build of PyTorch. Uninstall it (`pip uninstall torch torchvision`) and repeat step 2.

**3. Backend settings**

```bat
copy backend\.env.example backend\.env
```

Open `backend\.env` and change `ADMIN_PASSWORD` and `SECRET_KEY`.

**4. Database.** Pick one option.

- Install MongoDB Community Server and leave it running on port 27017.
- Or, if you have Docker: `docker run -d -p 27017:27017 --name cv-mongo mongo:7`
- Or skip MongoDB for now: set `USE_MOCK_DB=1` in `backend\.env`. Data is kept in memory and disappears when the server restarts, which is fine for quick testing.

**5. Portal**

```bat
cd frontend
npm install
cd ..
```

## Running it

Open two terminals in the project folder.

```bat
:: terminal 1
scripts\start_backend.bat

:: terminal 2
scripts\start_portal.bat
```

Open http://localhost:5173 and sign in with the admin details from `backend\.env`. The default is `admin` / `cleanvision`.

There are two ways to feed video in.

- **From the portal:** go to *Analyse footage* and upload a video. The backend runs the detector in the background and new incidents show up in the review queue.
- **From the command line**, which is better for live demos because you get a preview window:

```bat
python -m detector.run --source demo.mp4 --show
python -m detector.run --source 0 --show            :: laptop webcam
python -m detector.run --source demo.mp4 --no-api   :: only save evidence to storage\local_runs
```

The token in `config.yaml` (`api.token`) must match `DETECTOR_TOKEN` in `backend\.env`.

`config.yaml` starts with the stock `yolo11n.pt` COCO model, which already knows *person*, *bottle* and *cup*. You can test the whole system with a plastic bottle before training anything.

## Training your own model

**1. Get data**

```bat
git clone https://github.com/pedropro/TACO raw\TACO
python raw\TACO\download.py --dataset_path raw\TACO\data\annotations.json
```

TACO's images come from Flickr, so the download takes a while. Optionally add the Kaggle *Drinking Waste Classification* set and uncomment its block in `dataset\sources.yaml`.

**2. Record and label your own clips.** This is the most important step. Mount a phone high up, the way a CCTV camera would be, and record 20 to 30 short clips. Include littering, and also include non-littering actions such as putting a bottle down and picking it back up, or dropping something into a bin.

```bat
python dataset\extract_frames.py --videos raw\own\videos --out raw\own\frames --every 0.5
```

Label the frames in Roboflow or CVAT with the classes `person, bottle, can, wrapper, paper`. Export in YOLO format to `raw\own\export`, then uncomment the `own_footage` block in `dataset\sources.yaml`.

**3. Build the dataset**

```bat
python dataset\prepare_dataset.py --clean
```

This converts everything to YOLO format, maps TACO's 60 classes onto ours, fixes rotated phone photos, and adds person boxes automatically using the COCO model. It keeps all frames from one clip in the same split and prints how many boxes each class has.

**4. Train**

```bat
python training\train.py
```

This takes a few hours on a 3050. If you run out of memory, add `--imgsz 800`. Keep the laptop plugged in and on a performance power plan. When it finishes, set `model.weights` in `config.yaml` to `runs/detect/cleanvision/weights/best.pt`.

**5. Measure the littering rule** on test clips the model hasn't seen:

```bat
python tools\evaluate_events.py --videos test_clips --labels test_clips\labels.csv
```

This gives you precision, recall and F1 for the report. The CSV format is explained at the top of that script.

## Tuning

All of these live in `config.yaml`.

- `events.linger_s` is how long an object must sit untouched before it counts. Two seconds works for staged demos. Use 5 to 10 seconds for real footage.
- `events.separation` is how far the person must walk away, measured in body heights.
- `camera.bin_zones` marks areas where dropping things is fine. Draw them with `python tools\pick_zones.py --source demo.mp4`.
- `camera.ignore_zones` marks areas to ignore completely, such as a shop counter full of bottles.
- `model.vid_stride: 2` runs YOLO on every other frame when you need more speed.
- `events.verify_new_object` turns the "was this litter already there?" background check on or off.

## Tests

```bat
pytest
```

The tests cover the littering scenarios (dropping and walking away, putting down and picking up, old litter, bins, tracker ID switches, passers-by), the full API flow, dataset conversion, and the video pipeline including evidence writing. None of them need a GPU or MongoDB.

## Limitations

- Identity linking is simulated. An admin picks the person from a fictional registry after watching the clip. Real deployment would need authorised access to an identity system and a legal basis for issuing fines.
- Performance depends on camera angle, lighting, crowd density and occlusion. Crowded scenes with many overlapping people are the hardest case.
- Very small litter far from the camera, such as cigarette butts, is out of scope for this prototype.
- Evidence files are stored on local disk and served only to signed-in admins. A production system would need encrypted storage and retention rules.

## Troubleshooting

| Problem | Fix |
|---|---|
| `CUDA available: False` | You have the CPU build of PyTorch. Reinstall it from pytorch.org. |
| `CUDA out of memory` while training | Use `--imgsz 800`, close other GPU apps, or train `yolo11n` instead of `yolo11s`. |
| DataLoader errors on Windows | Use `--workers 0` or `--workers 2`. |
| Uploaded video job says "Failed" | Open the `detector.log` path shown in the error. It is usually a wrong `model.weights` path or `device: 0` on a machine without CUDA. |
| Portal shows "Can't reach the CleanVision server" | Start the backend (terminal 1) and check http://127.0.0.1:8000/api/health |
| Evidence video doesn't play | Clips are H.264 via `imageio-ffmpeg`. If that package is missing, OpenCV writes a format browsers can't play. Run `pip install imageio-ffmpeg`. |
| Detector upload returns 401 | `api.token` in `config.yaml` doesn't match `DETECTOR_TOKEN` in `backend\.env`. |