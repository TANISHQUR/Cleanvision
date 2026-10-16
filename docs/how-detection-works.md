# How CleanVision decides someone littered

Spotting a bottle on the ground is easy. Knowing that a particular person just dropped it is the hard part, because the bottle may have been lying there for hours. CleanVision solves this by watching how a person and an object behave together over several seconds. The code is in `detector/events.py` and is short enough to read in one sitting.

## Step 1: detect and track

Every frame goes through YOLO11, which returns boxes for people and litter (bottle, can, wrapper, paper). ByteTrack then gives each box a track ID that stays the same from frame to frame, so the system can say "person #3" and "bottle #7" instead of just "a person" and "a bottle".

## Step 2: give each object a holder

Each litter object remembers which person it belongs to. There are two ways an object gets a holder.

1. **Seen being carried.** The object is moving and sits inside or next to a person's box (the box is expanded by 25%). That person becomes the holder.
2. **Appears next to someone.** Small wrappers are often hidden in a hand, so the first time the model sees them is when they're already on the ground. If a new object shows up where a person was standing within the last second, that person becomes the holder.

If a new object appears with nobody nearby, it's marked **pre-existing** and can never trigger a violation. It was already there.

Once an object is resting on the ground, a different person walking past can't take over as holder. Ownership only changes if someone else is near the object *while it's moving* for at least 0.3 seconds, which means they picked it up.

## Step 3: wait for it to land and for the person to leave

An object counts as **stationary** when its centre has moved less than 2% of the frame height over the last second. A littering event fires when all of these are true:

- the object has a holder and is not pre-existing,
- it has been stationary for `linger_s` seconds (2 s in the demo config),
- the holder is either 0.8 body heights away from it or out of view for 0.7 s,
- the object is still visible.

Requiring the person to walk away is what separates littering from "put my bottle on the bench for a moment". If they pick it up again, the object starts moving and the timer resets.

## Step 4: filters that stop false alarms

- **Dustbin zones.** If the object lands inside a rectangle marked as a bin, nothing is reported.
- **Duplicates.** If an event was already reported at the same spot (IoU of 0.3 or more) in the last 60 seconds, the new one is dropped. This handles the tracker handing the same bottle a new ID.
- **ID inheritance.** When a new track appears exactly where a pre-existing or already-reported object just disappeared, it inherits that status. This matters because people walking in front of litter often cause ID switches.
- **Background check** (in `pipeline.py`). The system keeps a small grayscale snapshot every half second. When an event fires, it finds the most recent snapshot from before the person arrived in which nobody was blocking that spot. It then compares that patch with the current frame. If the patch looks the same, the litter was already there and the event is dropped. If it changed, the object is confirmed as new. If no clean earlier frame exists, the event is kept and the portal says so, and the reviewer decides.

## Step 5: evidence

The last 8 seconds of video are held in memory as JPEGs, which takes about 20 MB. When an event fires, the system records 2 more seconds and saves:

- `clip.mp4`: the whole sequence, with the linked person in orange and the object in red,
- `contact.jpg`: the last frame where the person was with the object before it landed,
- `scene.jpg`: the frame where the event fired, with the object on the ground,
- `event.json`: track IDs, times, confidence, and the background check result.

These are uploaded to the backend and appear in the review queue as *Waiting for review*.

## Step 6: a human decides

The system never issues a fine by itself. An admin watches the clip, picks the person from the (simulated) registry and approves the incident, which issues a challan. They can also dismiss it or mark it for a second look. Every decision is stored with the reviewer's name, time and note.

## Scenarios covered by tests

`tests/test_events.py` checks each of these with synthetic tracks:

| Scenario | Expected |
|---|---|
| Carries a bottle, drops it, walks on | 1 event, correct person |
| Puts a bottle down, stays, picks it up, leaves | nothing |
| Bottle already on the ground, person walks past, tracker changes its ID | nothing |
| Drops a bottle inside a bin zone | nothing |
| Carries a bottle the whole time | nothing |
| Stands still holding a bottle | nothing |
| Wrapper never seen in hand, appears at the person's feet, they leave | 1 event |
| Same litter gets a new track ID later | still only 1 event |
| Passer-by walks close to litter someone else just dropped | event blames the right person |
| Low-confidence detection | ignored |

`tests/test_pipeline.py` runs the full pipeline on a synthetic video and checks that old litter is caught by the background check.

## Known weak spots

- In a dense crowd, the nearest person to an object may not be the one who dropped it.
- A fast throw can land far from the thrower, outside the "near" area, so the object gets marked pre-existing. Increasing `near_margin` and `assoc_window_s` helps but raises false positives.
- If a person stands between the camera and the litter for the whole clip, the system never sees it land.
- The background check can be fooled by big lighting changes, such as a cloud passing or lights switching on.
